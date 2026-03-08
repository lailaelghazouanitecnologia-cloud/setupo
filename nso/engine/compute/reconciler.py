"""
Service reconciler — background loop that ensures desired state matches actual state.

Every RECONCILE_INTERVAL seconds:
1. Check each service's desired replicas vs actual
2. Detect offline nodes and relocate replicas
3. Enforce scaling policies (auto-scale based on metrics)
4. Clean up auto-provisioned nodes with no services
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from nso.shared import db

logger = logging.getLogger("nso.compute.reconciler")

RECONCILE_INTERVAL = 30  # seconds
OFFLINE_THRESHOLD = 90  # seconds since last heartbeat → offline
AUTO_DESTROY_IDLE = 600  # seconds idle before destroying auto-provisioned node

_task: asyncio.Task | None = None


async def _reconcile_once():
    """Single reconciliation pass."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # ── 1. Detect offline nodes ──
    all_nodes = await db.fetch_all("compute_nodes")
    for node in all_nodes:
        if node["status"] in ("offline", "maintenance", "pending", "provisioning"):
            continue
        last_hb = node.get("last_heartbeat", "")
        if last_hb:
            try:
                hb_time = datetime.fromisoformat(last_hb.replace("Z", "+00:00"))
                elapsed = (now - hb_time).total_seconds()
                if elapsed > OFFLINE_THRESHOLD and node["status"] == "online":
                    logger.warning("Node %s (%s) missed heartbeat (%.0fs), marking offline",
                                   node["id"], node.get("label", ""), elapsed)
                    await db.update("compute_nodes", node["id"], {
                        "status": "offline",
                        "agent_reachable": 0,
                        "updated_at": now_iso,
                    })
            except (ValueError, TypeError):
                pass

    # ── 2. Relocate replicas from offline nodes ──
    offline_nodes = await db.fetch_all("compute_nodes", status="offline")
    for node in offline_nodes:
        replicas = await db.fetch_all("service_replicas", instance_id=node["id"])
        active = [r for r in replicas if r.get("status") not in ("stopped", "failed", "destroyed")]
        if not active:
            continue

        for replica in active:
            svc = await db.fetch_one("service_registry", id=replica["service_id"])
            if not svc:
                continue

            # Only relocate if service placement allows it
            strategy = svc.get("placement_strategy", "shared")
            if strategy == "dedicated":
                # Dedicated: can't relocate, just mark as failed
                await db.update("service_replicas", replica["id"], {
                    "status": "failed",
                    "error": f"Node {node['id']} offline",
                    "updated_at": now_iso,
                })
                continue

            # Try to find a new node
            try:
                from nso.engine.compute.placement import find_placement
                existing = await db.fetch_all("service_replicas", service_id=svc["id"])
                exclude = {r["instance_id"] for r in existing
                           if r.get("status") not in ("stopped", "failed", "destroyed")}
                exclude.add(node["id"])

                candidates = await find_placement(svc["project_id"], svc, 1, exclude_nodes=exclude)
                if candidates:
                    new_node = candidates[0]
                    # Deploy to new node
                    from nso.engine.compute.supervisor_sync import apply_to_node as apply_to_agent
                    spec = _build_spec(svc)
                    await apply_to_agent(svc["project_id"], new_node["id"], [spec])

                    # Create new replica
                    import secrets
                    await db.insert("service_replicas", {
                        "id": f"rep_{secrets.token_hex(8)}",
                        "service_id": svc["id"],
                        "instance_id": new_node["id"],
                        "status": "pending",
                        "version": svc.get("version", ""),
                        "port": svc.get("port", 0),
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    })

                    # Mark old replica as destroyed
                    await db.update("service_replicas", replica["id"], {
                        "status": "destroyed",
                        "error": f"Relocated from offline node {node['id']}",
                        "updated_at": now_iso,
                    })

                    logger.info("Relocated replica %s from %s to %s",
                                replica["id"], node["id"], new_node["id"])
                else:
                    logger.warning("No candidates to relocate replica %s from offline node %s",
                                   replica["id"], node["id"])
            except Exception as e:
                logger.error("Failed to relocate replica %s: %s", replica["id"], e)

    # ── 3. Enforce scaling policies ──
    all_services = await db.fetch_all("service_registry")
    for svc in all_services:
        if svc.get("status") not in ("active",):
            continue

        policy = await db.fetch_one("scaling_policies", service_id=svc["id"])
        if not policy:
            continue

        # Check cooldown
        last_scale = policy.get("last_scale_at", "")
        if last_scale:
            try:
                last_time = datetime.fromisoformat(last_scale.replace("Z", "+00:00"))
                cooldown = policy.get("cooldown_seconds", 300)
                if (now - last_time).total_seconds() < cooldown:
                    continue
            except (ValueError, TypeError):
                pass

        replicas = await db.fetch_all("service_replicas", service_id=svc["id"])
        active = [r for r in replicas if r.get("status") not in ("stopped", "failed", "destroyed")]
        current = len(active)

        # Check min replicas
        if current < policy["min_replicas"] and current < policy["max_replicas"]:
            target = min(policy["min_replicas"], policy["max_replicas"])
            needed = target - current
            logger.info("Service %s below min replicas (%d < %d), scaling up by %d",
                        svc["id"], current, policy["min_replicas"], needed)
            await _auto_scale_up(svc, needed, active)
            await db.update("scaling_policies", policy["id"], {"last_scale_at": now_iso})
            continue

        # Metric-based scaling
        if current == 0:
            continue

        metric = policy.get("metric", "cpu")
        if metric == "cpu":
            values = [r.get("cpu_percent", 0) for r in active if r.get("cpu_percent") is not None]
        elif metric == "memory":
            values = [r.get("rss_mb", 0) for r in active if r.get("rss_mb") is not None]
        else:
            continue

        if not values:
            continue

        avg_value = sum(values) / len(values)
        target_val = policy["target_value"]

        # Scale up
        if avg_value > target_val and current < policy["max_replicas"]:
            step = policy.get("scale_up_step", 1)
            needed = min(step, policy["max_replicas"] - current)
            logger.info("Service %s avg %s=%.1f > target %.1f, scaling up by %d",
                        svc["id"], metric, avg_value, target_val, needed)
            await _auto_scale_up(svc, needed, active)
            await db.update("scaling_policies", policy["id"], {"last_scale_at": now_iso})

        # Scale down
        elif avg_value < target_val * 0.5 and current > policy["min_replicas"]:
            step = policy.get("scale_down_step", 1)
            excess = min(step, current - policy["min_replicas"])
            if excess > 0:
                logger.info("Service %s avg %s=%.1f < 50%% of target %.1f, scaling down by %d",
                            svc["id"], metric, avg_value, target_val, excess)
                await _auto_scale_down(svc, excess, active)
                await db.update("scaling_policies", policy["id"], {"last_scale_at": now_iso})

    # ── 4. Clean up idle auto-provisioned nodes ──
    for node in all_nodes:
        meta = node.get("metadata") or {}
        if not meta.get("auto_provisioned_for"):
            continue

        replicas = await db.fetch_all("service_replicas", instance_id=node["id"])
        active = [r for r in replicas if r.get("status") not in ("stopped", "failed", "destroyed")]
        if active:
            continue

        # Node has no active services — check idle time
        updated = node.get("updated_at", "")
        if updated:
            try:
                upd_time = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                idle_seconds = (now - upd_time).total_seconds()
                if idle_seconds > AUTO_DESTROY_IDLE:
                    logger.info("Destroying idle auto-provisioned node %s (idle %.0fs)",
                                node["id"], idle_seconds)
                    # Destroy the VPS
                    if node.get("instance_id"):
                        try:
                            from nso.engine.compute.service import delete_instance
                            await delete_instance(node["project_id"], node["instance_id"])
                        except Exception as e:
                            logger.error("Failed to destroy instance for node %s: %s", node["id"], e)
                    await db.delete("compute_nodes", node["id"])
            except (ValueError, TypeError):
                pass


def _build_spec(svc: dict) -> dict:
    """Build a ProcessSpec dict from a service registry entry."""
    spec = {
        "name": svc["name"],
        "command": svc.get("command", ""),
        "port": svc.get("port", 0),
        "working_dir": svc.get("working_dir", "/opt/app"),
        "health_path": svc.get("health_path", ""),
        "restart_policy": svc.get("restart_policy", "always"),
        "version": svc.get("version", ""),
    }
    env = svc.get("env")
    if isinstance(env, dict):
        spec["env"] = env
    return spec


async def _auto_scale_up(svc: dict, needed: int, active: list[dict]):
    """Scale up by deploying to new nodes via placement engine."""
    from nso.engine.compute.placement import find_placement
    from nso.engine.compute.supervisor_sync import apply_to_node as apply_to_agent
    import secrets

    exclude = {r["instance_id"] for r in active
               if r.get("status") not in ("stopped", "failed", "destroyed")}

    candidates = await find_placement(svc["project_id"], svc, needed, exclude_nodes=exclude)
    spec = _build_spec(svc)
    now = datetime.now(timezone.utc).isoformat()

    for node in candidates:
        try:
            await apply_to_agent(svc["project_id"], node["id"], [spec])
            await db.insert("service_replicas", {
                "id": f"rep_{secrets.token_hex(8)}",
                "service_id": svc["id"],
                "instance_id": node["id"],
                "status": "pending",
                "version": svc.get("version", ""),
                "port": svc.get("port", 0),
                "created_at": now,
                "updated_at": now,
            })
        except Exception as e:
            logger.error("Auto scale-up failed on node %s: %s", node["id"], e)


async def _auto_scale_down(svc: dict, excess: int, active: list[dict]):
    """Scale down by stopping newest replicas."""
    from nso.engine.compute.supervisor_sync import stop_on_node as agent_stop

    to_remove = sorted(active, key=lambda r: r.get("created_at", ""), reverse=True)[:excess]
    now = datetime.now(timezone.utc).isoformat()

    for replica in to_remove:
        try:
            await agent_stop(svc["project_id"], replica["instance_id"], svc["name"])
            await db.update("service_replicas", replica["id"], {
                "status": "stopped",
                "updated_at": now,
            })
        except Exception as e:
            logger.error("Auto scale-down failed for replica %s: %s", replica["id"], e)


# ── Background loop ──


async def _reconciler_loop():
    """Background loop that reconciles every RECONCILE_INTERVAL seconds."""
    logger.info("Reconciler started (interval=%ds)", RECONCILE_INTERVAL)
    while True:
        try:
            await _reconcile_once()
        except Exception as e:
            logger.error("Reconciliation error: %s", e)
        await asyncio.sleep(RECONCILE_INTERVAL)


def start_reconciler():
    """Start the background reconciler task."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_reconciler_loop())
        logger.info("Reconciler task started")


def stop_reconciler():
    """Stop the background reconciler task."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        _task = None
