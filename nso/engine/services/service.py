"""
Service registry — central management of services, replicas, scaling and connections.

A service is the runtime representation of a workspace (or part of one).
Services run as replicas across instances, can scale, and connect to other resources.
"""

import logging
import secrets
from datetime import datetime, timezone

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, ValidationError

logger = logging.getLogger("nso.services")


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Service Registry CRUD ──


async def create_service(project_id: str, name: str, **kwargs) -> dict:
    """Register a new service in the project."""
    existing = await db.fetch_one("service_registry", project_id=project_id, name=name)
    if existing:
        raise ConflictError(f"Service '{name}' already exists in this project")

    service_id = _gen_id("svc")
    now = _now()

    data = {
        "id": service_id,
        "project_id": project_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
    }

    # Optional fields
    for field in (
        "workspace_id", "version", "status", "service_type",
        "cpu_request", "cpu_limit", "mem_request_mb", "mem_limit_mb",
        "scaling_min", "scaling_max", "scaling_target_cpu",
        "command", "port", "health_path", "working_dir", "env",
        "restart_policy", "endpoints", "dependencies", "connects_to",
        "metadata",
    ):
        if field in kwargs and kwargs[field] is not None:
            data[field] = kwargs[field]

    await db.insert("service_registry", data)

    # Auto-create scaling policy if scaling params provided
    if kwargs.get("scaling_min") or kwargs.get("scaling_max"):
        await _ensure_scaling_policy(service_id, kwargs)

    await _emit_event(service_id, None, "created", f"Service '{name}' registered")
    logger.info("Created service %s (%s) for project %s", service_id, name, project_id)

    return await db.fetch_one("service_registry", id=service_id)


async def get_service(project_id: str, service_id: str) -> dict:
    """Get a service by ID."""
    svc = await db.fetch_one("service_registry", id=service_id)
    if not svc or svc["project_id"] != project_id:
        raise NotFoundError("Service", service_id)
    return svc


async def get_service_by_name(project_id: str, name: str) -> dict:
    """Get a service by name within a project."""
    svc = await db.fetch_one("service_registry", project_id=project_id, name=name)
    if not svc:
        raise NotFoundError("Service", name)
    return svc


async def list_services(project_id: str, status: str = "", service_type: str = "") -> list[dict]:
    """List all services for a project, optionally filtered."""
    filters = {"project_id": project_id}
    if status:
        filters["status"] = status
    if service_type:
        filters["service_type"] = service_type
    return await db.fetch_all("service_registry", order_by="name ASC", **filters)


async def update_service(project_id: str, service_id: str, **updates) -> dict:
    """Update a service's configuration."""
    svc = await get_service(project_id, service_id)

    allowed = {
        "version", "status", "service_type",
        "cpu_request", "cpu_limit", "mem_request_mb", "mem_limit_mb",
        "scaling_min", "scaling_max", "scaling_target_cpu",
        "command", "port", "health_path", "working_dir", "env",
        "restart_policy", "endpoints", "dependencies", "connects_to",
        "metadata", "workspace_id",
    }

    data = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not data:
        return svc

    data["updated_at"] = _now()
    await db.update("service_registry", service_id, data)

    # Sync scaling policy if scaling params changed
    scaling_fields = {"scaling_min", "scaling_max", "scaling_target_cpu"}
    if scaling_fields & set(data.keys()):
        merged = {**svc, **data}
        await _ensure_scaling_policy(service_id, merged)

    await _emit_event(service_id, None, "updated", f"Updated: {', '.join(data.keys())}")
    return await db.fetch_one("service_registry", id=service_id)


async def delete_service(project_id: str, service_id: str):
    """Delete a service and all its replicas, events, connections."""
    await get_service(project_id, service_id)
    await db.delete("service_registry", service_id)  # CASCADE handles replicas, events, policy
    # Clean up resource_connections referencing this service
    conn = await db.get_db()
    await conn.execute(
        "DELETE FROM resource_connections WHERE "
        "(source_type = 'service' AND source_id = ?) OR "
        "(target_type = 'service' AND target_id = ?)",
        (service_id, service_id),
    )
    await conn.commit()
    logger.info("Deleted service %s", service_id)


# ── Replicas ──


async def list_replicas(service_id: str) -> list[dict]:
    """List all replicas of a service."""
    return await db.fetch_all("service_replicas", order_by="created_at ASC", service_id=service_id)


async def add_replica(service_id: str, instance_id: str, **kwargs) -> dict:
    """Add a replica of a service on an instance."""
    existing = await db.fetch_one(
        "service_replicas", service_id=service_id, instance_id=instance_id,
    )
    if existing:
        raise ConflictError(f"Service already has a replica on instance {instance_id}")

    replica_id = _gen_id("rep")
    now = _now()

    data = {
        "id": replica_id,
        "service_id": service_id,
        "instance_id": instance_id,
        "status": kwargs.get("status", "pending"),
        "version": kwargs.get("version", ""),
        "port": kwargs.get("port", 0),
        "created_at": now,
        "updated_at": now,
    }
    await db.insert("service_replicas", data)

    svc = await db.fetch_one("service_registry", id=service_id)
    await _emit_event(service_id, instance_id, "replica_added",
                      f"Replica added on instance {instance_id}")
    logger.info("Added replica %s for service %s on instance %s", replica_id, service_id, instance_id)

    return await db.fetch_one("service_replicas", id=replica_id)


async def remove_replica(service_id: str, instance_id: str):
    """Remove a replica from an instance."""
    replica = await db.fetch_one(
        "service_replicas", service_id=service_id, instance_id=instance_id,
    )
    if not replica:
        raise NotFoundError("Replica", f"{service_id}/{instance_id}")

    await db.delete("service_replicas", replica["id"])
    await _emit_event(service_id, instance_id, "replica_removed",
                      f"Replica removed from instance {instance_id}")


async def update_replica(replica_id: str, **updates) -> dict:
    """Update a replica's observed state (from metrics sync)."""
    allowed = {"status", "pid", "port", "version", "cpu_percent", "rss_mb",
               "uptime", "error", "collected_at"}
    data = {k: v for k, v in updates.items() if k in allowed}
    if data:
        data["updated_at"] = _now()
        await db.update("service_replicas", replica_id, data)
    return await db.fetch_one("service_replicas", id=replica_id)


async def get_replica_count(service_id: str) -> int:
    """Count active replicas for a service."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM service_replicas "
        "WHERE service_id = ? AND status NOT IN ('stopped', 'failed', 'destroyed')",
        (service_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


# ── Scaling ──


async def get_scaling_policy(service_id: str) -> dict | None:
    """Get the scaling policy for a service."""
    return await db.fetch_one("scaling_policies", service_id=service_id)


async def set_scaling_policy(service_id: str, **kwargs) -> dict:
    """Create or update a scaling policy."""
    existing = await db.fetch_one("scaling_policies", service_id=service_id)
    now = _now()

    data = {}
    for field in ("min_replicas", "max_replicas", "metric", "target_value",
                  "cooldown_seconds", "scale_up_step", "scale_down_step"):
        if field in kwargs and kwargs[field] is not None:
            data[field] = kwargs[field]

    if not data:
        if existing:
            return existing
        raise ValidationError("No scaling parameters provided")

    data["updated_at"] = now

    if existing:
        await db.update("scaling_policies", existing["id"], data)
        await _emit_event(service_id, None, "scaling_updated",
                          f"Scaling policy updated: {', '.join(data.keys())}")
    else:
        data["id"] = _gen_id("sp")
        data["service_id"] = service_id
        data["created_at"] = now
        data.setdefault("min_replicas", 1)
        data.setdefault("max_replicas", 1)
        await db.insert("scaling_policies", data)
        await _emit_event(service_id, None, "scaling_created", "Scaling policy created")

    return await db.fetch_one("scaling_policies", service_id=service_id)


async def evaluate_scaling(service_id: str) -> dict:
    """
    Evaluate if a service needs to scale up or down based on its policy
    and current replica metrics. Returns scaling recommendation.
    """
    policy = await get_scaling_policy(service_id)
    if not policy:
        return {"action": "none", "reason": "no scaling policy"}

    replicas = await list_replicas(service_id)
    active = [r for r in replicas if r.get("status") in ("running", "pending", "starting")]
    current_count = len(active)

    if current_count == 0:
        if policy["min_replicas"] > 0:
            return {
                "action": "scale_up",
                "current": 0,
                "target": policy["min_replicas"],
                "reason": "below minimum replicas",
            }
        return {"action": "none", "reason": "no active replicas, min is 0"}

    # Calculate average metric
    metric = policy["metric"]
    if metric == "cpu":
        values = [r.get("cpu_percent", 0) for r in active if r.get("cpu_percent") is not None]
    elif metric == "memory":
        values = [r.get("rss_mb", 0) for r in active if r.get("rss_mb") is not None]
    else:
        values = []

    if not values:
        return {"action": "none", "reason": f"no {metric} data available"}

    avg_value = sum(values) / len(values)
    target = policy["target_value"]

    # Scale up
    if avg_value > target and current_count < policy["max_replicas"]:
        new_count = min(current_count + policy["scale_up_step"], policy["max_replicas"])
        return {
            "action": "scale_up",
            "current": current_count,
            "target": new_count,
            "metric": metric,
            "avg_value": round(avg_value, 1),
            "threshold": target,
            "reason": f"avg {metric} ({avg_value:.1f}) > target ({target})",
        }

    # Scale down
    if avg_value < target * 0.5 and current_count > policy["min_replicas"]:
        new_count = max(current_count - policy["scale_down_step"], policy["min_replicas"])
        if new_count < current_count:
            return {
                "action": "scale_down",
                "current": current_count,
                "target": new_count,
                "metric": metric,
                "avg_value": round(avg_value, 1),
                "threshold": target * 0.5,
                "reason": f"avg {metric} ({avg_value:.1f}) < 50% of target ({target})",
            }

    return {
        "action": "none",
        "current": current_count,
        "metric": metric,
        "avg_value": round(avg_value, 1),
        "reason": "within target range",
    }


async def scale_service(project_id: str, service_id: str, replicas: int) -> dict:
    """
    Manually set the desired replica count for a service.
    Updates the scaling policy min/max to match.
    """
    svc = await get_service(project_id, service_id)
    policy = await get_scaling_policy(service_id)

    if replicas < 0:
        raise ValidationError("Replica count cannot be negative")
    if replicas > 50:
        raise ValidationError("Maximum 50 replicas per service")

    current = await get_replica_count(service_id)

    if policy:
        await db.update("scaling_policies", policy["id"], {
            "min_replicas": replicas,
            "max_replicas": max(replicas, policy.get("max_replicas", replicas)),
            "updated_at": _now(),
        })
    else:
        await set_scaling_policy(service_id, min_replicas=replicas, max_replicas=replicas)

    await _emit_event(service_id, None, "scaled",
                      f"Scaled from {current} to {replicas} replicas")

    return {
        "service_id": service_id,
        "previous_replicas": current,
        "target_replicas": replicas,
    }


# ── Resource Connections ──


async def create_connection(
    project_id: str,
    source_type: str, source_id: str,
    target_type: str, target_id: str,
    config: dict | None = None,
) -> dict:
    """Create a connection between two resources (e.g. service → database)."""
    valid_types = {"service", "database", "bucket", "instance", "workspace", "external"}
    if source_type not in valid_types:
        raise ValidationError(f"Invalid source_type: {source_type}. Must be one of: {valid_types}")
    if target_type not in valid_types:
        raise ValidationError(f"Invalid target_type: {target_type}. Must be one of: {valid_types}")

    # Check for duplicate
    existing = await db.fetch_one(
        "resource_connections",
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        target_id=target_id,
    )
    if existing:
        raise ConflictError("Connection already exists")

    conn_id = _gen_id("conn")
    now = _now()
    await db.insert("resource_connections", {
        "id": conn_id,
        "project_id": project_id,
        "source_type": source_type,
        "source_id": source_id,
        "target_type": target_type,
        "target_id": target_id,
        "config": config or {},
        "status": "active",
        "created_at": now,
        "updated_at": now,
    })

    logger.info("Created connection %s: %s/%s → %s/%s",
                conn_id, source_type, source_id, target_type, target_id)

    return await db.fetch_one("resource_connections", id=conn_id)


async def list_connections(project_id: str, resource_type: str = "", resource_id: str = "") -> list[dict]:
    """List connections, optionally filtered by a resource (as source or target)."""
    if resource_type and resource_id:
        conn = await db.get_db()
        cursor = await conn.execute(
            "SELECT * FROM resource_connections WHERE project_id = ? AND "
            "((source_type = ? AND source_id = ?) OR (target_type = ? AND target_id = ?)) "
            "ORDER BY created_at DESC",
            (project_id, resource_type, resource_id, resource_type, resource_id),
        )
        rows = await cursor.fetchall()
        return [db._row_to_dict(r) for r in rows]

    return await db.fetch_all("resource_connections", project_id=project_id)


async def delete_connection(project_id: str, connection_id: str):
    """Delete a resource connection."""
    conn_rec = await db.fetch_one("resource_connections", id=connection_id)
    if not conn_rec or conn_rec["project_id"] != project_id:
        raise NotFoundError("Connection", connection_id)
    await db.delete("resource_connections", connection_id)


# ── Events ──


async def list_events(service_id: str, limit: int = 50) -> list[dict]:
    """List recent events for a service."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM service_events WHERE service_id = ? ORDER BY created_at DESC LIMIT ?",
        (service_id, limit),
    )
    rows = await cursor.fetchall()
    return [db._row_to_dict(r) for r in rows]


# ── Service overview (aggregate) ──


async def get_service_overview(project_id: str, service_id: str) -> dict:
    """Get full overview: service + replicas + scaling + connections + recent events."""
    svc = await get_service(project_id, service_id)
    replicas = await list_replicas(service_id)
    policy = await get_scaling_policy(service_id)
    connections = await list_connections(project_id, "service", service_id)
    events = await list_events(service_id, limit=20)
    scaling_eval = await evaluate_scaling(service_id)

    # Aggregate resource usage
    active_replicas = [r for r in replicas if r.get("status") in ("running", "pending", "starting")]
    total_cpu = sum(r.get("cpu_percent", 0) for r in active_replicas)
    total_rss = sum(r.get("rss_mb", 0) for r in active_replicas)

    return {
        "service": svc,
        "replicas": replicas,
        "replica_count": len(active_replicas),
        "scaling_policy": policy,
        "scaling_recommendation": scaling_eval,
        "connections": connections,
        "events": events,
        "resources": {
            "total_cpu_percent": round(total_cpu, 1),
            "total_rss_mb": round(total_rss, 1),
            "avg_cpu_percent": round(total_cpu / len(active_replicas), 1) if active_replicas else 0,
            "avg_rss_mb": round(total_rss / len(active_replicas), 1) if active_replicas else 0,
        },
    }


# ── Deploy service to instance(s) ──


async def deploy_service(project_id: str, service_id: str, instance_ids: list[str]) -> dict:
    """
    Deploy a service to one or more instances via their agents.
    Creates replicas and sends supervisor apply commands.
    """
    from nso.engine.compute.services import apply_services as apply_to_agent
    from nso.engine.compute.service import get_instance

    svc = await get_service(project_id, service_id)
    results = []

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

    for iid in instance_ids:
        try:
            inst = await get_instance(project_id, iid)

            # Send to agent supervisor
            await apply_to_agent(project_id, iid, [spec])

            # Create or update replica record
            existing = await db.fetch_one(
                "service_replicas", service_id=service_id, instance_id=iid,
            )
            if existing:
                await update_replica(existing["id"], status="pending", version=svc.get("version", ""))
            else:
                await add_replica(service_id, iid,
                                  version=svc.get("version", ""),
                                  port=svc.get("port", 0))

            results.append({"instance_id": iid, "status": "deployed"})
        except Exception as e:
            logger.error("Failed to deploy service %s to instance %s: %s", service_id, iid, e)
            results.append({"instance_id": iid, "status": "failed", "error": str(e)})

    await update_service(project_id, service_id, status="active")
    await _emit_event(service_id, None, "deployed",
                      f"Deployed to {len(instance_ids)} instance(s)")

    return {"service_id": service_id, "results": results}


# ── Internal helpers ──


async def _ensure_scaling_policy(service_id: str, params: dict):
    """Create or update scaling policy from service params."""
    await set_scaling_policy(
        service_id,
        min_replicas=params.get("scaling_min", 1),
        max_replicas=params.get("scaling_max", 1),
        target_value=params.get("scaling_target_cpu", 70.0),
    )


async def _emit_event(service_id: str, instance_id: str | None,
                       event_type: str, message: str, metadata: dict | None = None):
    """Record a service event."""
    await db.insert("service_events", {
        "id": _gen_id("evt"),
        "service_id": service_id,
        "instance_id": instance_id,
        "event_type": event_type,
        "message": message,
        "metadata": metadata or {},
        "created_at": _now(),
    })
