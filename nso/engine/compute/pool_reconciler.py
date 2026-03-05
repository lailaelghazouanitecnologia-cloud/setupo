"""
Pool Reconciler — manages VM lifecycle on hosts.

Runs alongside the main reconciler. Handles:
1. Creating containers/processes for allocated VMs on hosts
2. Monitoring VM health via host agent
3. Migrating VMs when hosts drain
4. Tracking resource usage per VM

This is the bridge between pool allocation (DB records) and
actual VM creation on hosts (via host agent HTTP API).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from nso.shared import db
from nso.shared.events import emit
from nso.engine.compute import pool

logger = logging.getLogger("nso.compute.pool_reconciler")

POOL_RECONCILE_INTERVAL = 15  # seconds
HOST_AGENT_PORT = 8081
HOST_AGENT_TIMEOUT = 10

_pool_task: asyncio.Task | None = None


async def start_pool_reconciler():
    """Start the pool reconciler loop."""
    global _pool_task
    if _pool_task and not _pool_task.done():
        return
    _pool_task = asyncio.create_task(_pool_loop())
    logger.info("Pool reconciler started (interval=%ds)", POOL_RECONCILE_INTERVAL)


async def stop_pool_reconciler():
    """Stop the pool reconciler loop."""
    global _pool_task
    if _pool_task and not _pool_task.done():
        _pool_task.cancel()
        try:
            await _pool_task
        except asyncio.CancelledError:
            pass
    _pool_task = None
    logger.info("Pool reconciler stopped")


async def _pool_loop():
    """Main pool reconciliation loop."""
    while True:
        try:
            await _reconcile_pool()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Pool reconciler error: %s", e, exc_info=True)
        await asyncio.sleep(POOL_RECONCILE_INTERVAL)


async def _reconcile_pool():
    """Single sweep — reconcile all VMs and hosts."""
    # 1. Check host health
    hosts = await pool.list_hosts(status="active")
    for host in hosts:
        await _check_host_health(host)

    # 2. Reconcile VMs
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM compute_vms WHERE status NOT IN ('destroyed', 'error')"
    )
    vms = await cursor.fetchall()

    for vm_row in vms:
        vm = dict(vm_row)
        try:
            await _reconcile_vm(vm)
        except Exception as e:
            logger.error("Error reconciling VM %s: %s", vm["id"], e)

    # 3. Handle draining hosts — migrate VMs away
    draining_hosts = await pool.list_hosts(status="draining")
    for host in draining_hosts:
        await _handle_draining_host(host)


async def _check_host_health(host: dict):
    """Check host agent health and update metrics."""
    ip = host.get("ip", "")
    if not ip:
        return

    try:
        async with httpx.AsyncClient(timeout=HOST_AGENT_TIMEOUT) as client:
            resp = await client.get(f"http://{ip}:{HOST_AGENT_PORT}/health")
            if resp.status_code == 200:
                data = resp.json()
                system = data.get("system", {})
                await pool.update_host_metrics(
                    host["id"],
                    cpu=system.get("cpu_percent", 0),
                    ram=system.get("mem_percent", 0),
                    disk=system.get("disk_percent", 0),
                )
    except Exception:
        # Host unreachable — check if it's been down too long
        last_hb = host.get("last_heartbeat", "")
        if last_hb:
            try:
                last = datetime.fromisoformat(last_hb)
                age = (datetime.now(timezone.utc) - last).total_seconds()
                if age > 300:  # 5 minutes without heartbeat
                    logger.warning("Host %s unreachable for %ds", host["id"], int(age))
                    await emit("host.unreachable", {
                        "host_id": host["id"],
                        "ip": ip,
                        "seconds_since_heartbeat": int(age),
                    }, source="pool_reconciler")
            except Exception:
                pass


async def _reconcile_vm(vm: dict):
    """Reconcile a single VM on its host."""
    status = vm.get("status", "")
    host_id = vm["host_id"]
    vm_id = vm["id"]

    # Get host info
    host = await pool.get_host(host_id)
    if not host:
        logger.error("VM %s references non-existent host %s", vm_id, host_id)
        await pool.set_vm_status(vm_id, "error")
        return

    host_ip = host.get("ip", "")
    if not host_ip:
        return

    if status == "creating":
        # Send create command to host agent
        created = await _create_vm_on_host(host_ip, vm, host)
        if created:
            await pool.set_vm_status(vm_id, "running")
            await emit("vm.started", {
                "vm_id": vm_id,
                "host_id": host_id,
                "project_id": vm["project_id"],
            }, source="pool_reconciler")
        # If not created, retry next sweep

    elif status == "running":
        # Check if VM process is still alive on host
        alive = await _check_vm_on_host(host_ip, vm_id, host)
        if not alive:
            logger.warning("VM %s not found on host %s, restarting", vm_id, host_id)
            await _create_vm_on_host(host_ip, vm, host)

    elif status == "stopping":
        await _stop_vm_on_host(host_ip, vm_id, host)
        await pool.set_vm_status(vm_id, "stopped")


async def _handle_draining_host(host: dict):
    """Migrate VMs off a draining host to other hosts."""
    host_id = host["id"]
    vms = await pool.list_vms(host_id=host_id)
    active_vms = [v for v in vms if v.get("status") in ("running", "creating")]

    if not active_vms:
        # No more VMs — mark host as offline
        await pool.set_host_status(host_id, "offline")
        await emit("host.drained", {"host_id": host_id}, source="pool_reconciler")
        logger.info("Host %s fully drained, marked offline", host_id)
        return

    for vm in active_vms:
        plan_id = vm.get("plan_id", "")
        plan = None
        if plan_id:
            # Look up plan by id
            conn = await db.get_db()
            cursor = await conn.execute("SELECT * FROM compute_plans WHERE id = ?", (plan_id,))
            row = await cursor.fetchone()
            if row:
                plan = dict(row)

        if not plan:
            continue

        # Try to find another host
        new_host = await pool._find_best_host(
            vm["vcpus"], vm["ram_mb"], vm["disk_gb"],
            region=host.get("region", ""),
        )
        if not new_host or new_host["id"] == host_id:
            logger.warning("Cannot migrate VM %s — no available host", vm["id"])
            continue

        # Stop on old host
        await _stop_vm_on_host(host.get("ip", ""), vm["id"], host)

        # Update VM record to new host
        await db.update("compute_vms", vm["id"], {
            "host_id": new_host["id"],
            "ip_external": new_host["ip"],
            "status": "creating",  # will be picked up next sweep
        })

        # Update resource counts
        await db.update("compute_hosts", host_id, {
            "vcpus_used": max(0, host.get("vcpus_used", 0) - vm["vcpus"]),
            "ram_mb_used": max(0, host.get("ram_mb_used", 0) - vm["ram_mb"]),
            "disk_gb_used": max(0, host.get("disk_gb_used", 0) - vm["disk_gb"]),
        })
        await db.update("compute_hosts", new_host["id"], {
            "vcpus_used": new_host.get("vcpus_used", 0) + vm["vcpus"],
            "ram_mb_used": new_host.get("ram_mb_used", 0) + vm["ram_mb"],
            "disk_gb_used": new_host.get("disk_gb_used", 0) + vm["disk_gb"],
        })

        await emit("vm.migrated", {
            "vm_id": vm["id"],
            "from_host": host_id,
            "to_host": new_host["id"],
        }, source="pool_reconciler")

        logger.info("VM %s migrated from host %s to %s", vm["id"], host_id, new_host["id"])


# ── Host agent communication ──

async def _create_vm_on_host(host_ip: str, vm: dict, host: dict) -> bool:
    """Tell host agent to create a VM/container."""
    try:
        async with httpx.AsyncClient(timeout=HOST_AGENT_TIMEOUT) as client:
            resp = await client.post(
                f"http://{host_ip}:{HOST_AGENT_PORT}/pool/vms",
                json={
                    "vm_id": vm["id"],
                    "project_id": vm["project_id"],
                    "vcpus": vm["vcpus"],
                    "ram_mb": vm["ram_mb"],
                    "disk_gb": vm["disk_gb"],
                    "port_start": vm["port_start"],
                    "port_end": vm["port_end"],
                },
                headers=_host_auth(host),
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                # Update container info
                updates = {}
                if data.get("container_id"):
                    updates["container_id"] = data["container_id"]
                if data.get("pid"):
                    updates["pid"] = data["pid"]
                if data.get("ip_internal"):
                    updates["ip_internal"] = data["ip_internal"]
                if updates:
                    await db.update("compute_vms", vm["id"], updates)
                return True
            else:
                logger.warning("Failed to create VM %s on host %s: %s", vm["id"], host_ip, resp.text)
    except Exception as e:
        logger.warning("Failed to create VM %s on host %s: %s", vm["id"], host_ip, e)
    return False


async def _check_vm_on_host(host_ip: str, vm_id: str, host: dict) -> bool:
    """Check if VM is alive on host."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://{host_ip}:{HOST_AGENT_PORT}/pool/vms/{vm_id}",
                headers=_host_auth(host),
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") in ("running", "creating")
    except Exception:
        pass
    return False


async def _stop_vm_on_host(host_ip: str, vm_id: str, host: dict) -> bool:
    """Tell host to stop a VM."""
    try:
        async with httpx.AsyncClient(timeout=HOST_AGENT_TIMEOUT) as client:
            resp = await client.delete(
                f"http://{host_ip}:{HOST_AGENT_PORT}/pool/vms/{vm_id}",
                headers=_host_auth(host),
            )
            return resp.status_code in (200, 204, 404)
    except Exception:
        return False


def _host_auth(host: dict) -> dict:
    """Build auth headers for host agent."""
    token = host.get("agent_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
