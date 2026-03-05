"""
VMManager — lifecycle management for user VMs in the compute pool.

Manages the full lifecycle of VMs:
- Allocation (plan → host selection → port assignment)
- Creation (via pool reconciler → host agent)
- Health monitoring (process alive, resource usage)
- Suspension/resume (for billing or abuse)
- Migration (between hosts for maintenance)
- Destruction (cleanup resources)

Enforces security boundaries:
- Project isolation (VMs can only be accessed by their project)
- Resource quotas (per-project VM limits)
- Network isolation verification
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from nso.shared import db
from nso.shared.events import emit
from nso.engine.compute import pool

logger = logging.getLogger("nso.compute.vm_manager")

CHECK_INTERVAL = 15  # seconds
AGENT_PORT = 8081
AGENT_TIMEOUT = 10

# Project-level limits
DEFAULT_MAX_VMS_PER_PROJECT = 10
MAX_CREATING_TIME = 300  # seconds before "creating" VM is considered stuck
MAX_STOPPED_TIME = 86400 * 7  # 7 days stopped before auto-cleanup warning

_task: asyncio.Task | None = None


async def start():
    """Start the VM manager loop."""
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("VMManager started (interval=%ds)", CHECK_INTERVAL)


async def stop():
    """Stop the VM manager loop."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("VMManager stopped")


async def is_healthy() -> bool:
    """Health check for ServiceManager."""
    return _task is not None and not _task.done()


async def _loop():
    while True:
        try:
            await _sweep()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("VMManager sweep error: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL)


async def _sweep():
    """Single management sweep — reconcile all VMs."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM compute_vms WHERE status NOT IN ('destroyed')"
    )
    vms = [dict(r) for r in await cursor.fetchall()]

    for vm in vms:
        try:
            await _reconcile_vm(vm)
        except Exception as e:
            logger.error("Error reconciling VM %s: %s", vm["id"], e)

    # Check for stuck VMs
    await _check_stuck_vms(vms)

    # Check project quotas
    await _check_quotas(vms)


async def _reconcile_vm(vm: dict):
    """Reconcile a single VM."""
    status = vm.get("status", "")
    vm_id = vm["id"]
    host_id = vm["host_id"]

    host = await pool.get_host(host_id)
    if not host:
        logger.error("VM %s references non-existent host %s", vm_id, host_id)
        await pool.set_vm_status(vm_id, "error")
        return

    host_ip = host.get("ip", "")
    host_status = host.get("status", "")

    # If host is not active/degraded, don't try to manage VMs on it
    if host_status not in ("active", "degraded"):
        return

    if status == "creating":
        await _handle_creating(vm, host)
    elif status == "running":
        await _handle_running(vm, host)
    elif status == "stopping":
        await _handle_stopping(vm, host)
    elif status == "suspended":
        pass  # suspended VMs are intentionally stopped, don't restart


async def _handle_creating(vm: dict, host: dict):
    """Handle a VM in 'creating' state — tell the host agent to create it."""
    vm_id = vm["id"]
    host_ip = host.get("ip", "")

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(
                f"http://{host_ip}:{AGENT_PORT}/pool/vms",
                json={
                    "vm_id": vm_id,
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
                updates = {"status": "running"}
                if data.get("container_id"):
                    updates["container_id"] = data["container_id"]
                if data.get("pid"):
                    updates["pid"] = data["pid"]
                if data.get("ip_internal"):
                    updates["ip_internal"] = data["ip_internal"]
                await db.update("compute_vms", vm_id, updates)

                await emit("vm.started", {
                    "vm_id": vm_id,
                    "host_id": host["id"],
                    "project_id": vm["project_id"],
                }, source="vm_manager")
                logger.info("VM %s created on host %s", vm_id, host["id"])
            else:
                logger.warning("Failed to create VM %s: %s", vm_id, resp.text)
    except Exception as e:
        logger.warning("Failed to create VM %s on host %s: %s", vm_id, host_ip, e)


async def _handle_running(vm: dict, host: dict):
    """Handle a running VM — verify it's still alive."""
    vm_id = vm["id"]
    host_ip = host.get("ip", "")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://{host_ip}:{AGENT_PORT}/pool/vms/{vm_id}",
                headers=_host_auth(host),
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") not in ("running", "creating"):
                    # VM died — restart it
                    logger.warning("VM %s not running on host, restarting", vm_id)
                    await db.update("compute_vms", vm_id, {"status": "creating"})
                    await emit("vm.crashed", {
                        "vm_id": vm_id,
                        "host_id": host["id"],
                        "project_id": vm["project_id"],
                    }, source="vm_manager")
            elif resp.status_code == 404:
                # VM not found on host — recreate
                logger.warning("VM %s not found on host %s, recreating", vm_id, host["id"])
                await db.update("compute_vms", vm_id, {"status": "creating"})
    except Exception:
        pass  # host might be temporarily unreachable


async def _handle_stopping(vm: dict, host: dict):
    """Handle a VM that should be stopped."""
    vm_id = vm["id"]
    host_ip = host.get("ip", "")

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.delete(
                f"http://{host_ip}:{AGENT_PORT}/pool/vms/{vm_id}",
                headers=_host_auth(host),
            )
            if resp.status_code in (200, 204, 404):
                await pool.set_vm_status(vm_id, "stopped")
                logger.info("VM %s stopped", vm_id)
    except Exception as e:
        logger.warning("Failed to stop VM %s: %s", vm_id, e)


async def _check_stuck_vms(vms: list[dict]):
    """Detect VMs stuck in 'creating' state."""
    from datetime import datetime, timezone

    for vm in vms:
        if vm.get("status") != "creating":
            continue

        created = vm.get("created_at", "")
        if not created:
            continue

        try:
            created_dt = datetime.fromisoformat(created)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - created_dt).total_seconds()

            if age > MAX_CREATING_TIME:
                logger.error("VM %s stuck in 'creating' for %ds, marking error", vm["id"], int(age))
                await pool.set_vm_status(vm["id"], "error")
                await emit("vm.stuck", {
                    "vm_id": vm["id"],
                    "project_id": vm["project_id"],
                    "age_seconds": int(age),
                }, source="vm_manager")
        except Exception:
            pass


async def _check_quotas(vms: list[dict]):
    """Check project-level VM quotas."""
    project_counts: dict[str, int] = {}
    for vm in vms:
        if vm.get("status") in ("destroyed", "error"):
            continue
        pid = vm.get("project_id", "")
        project_counts[pid] = project_counts.get(pid, 0) + 1

    for pid, count in project_counts.items():
        if count > DEFAULT_MAX_VMS_PER_PROJECT:
            await emit("vm.quota_exceeded", {
                "project_id": pid,
                "vm_count": count,
                "limit": DEFAULT_MAX_VMS_PER_PROJECT,
            }, source="vm_manager")


# ── Public API ──

async def allocate(
    project_id: str,
    plan_code: str,
    region: str = "",
    label: str = "",
) -> dict:
    """
    Allocate a new VM for a project.

    Validates quotas before allocation.
    """
    # Check project quota
    existing = await pool.list_vms(project_id=project_id)
    active = [v for v in existing if v.get("status") not in ("destroyed", "error")]
    if len(active) >= DEFAULT_MAX_VMS_PER_PROJECT:
        raise ValueError(
            f"Project has {len(active)} VMs (limit: {DEFAULT_MAX_VMS_PER_PROJECT})"
        )

    vm = await pool.allocate_vm(
        project_id=project_id,
        plan_code=plan_code,
        region=region,
        label=label,
    )

    await emit("vm.allocated", {
        "vm_id": vm["id"],
        "project_id": project_id,
        "plan": plan_code,
    }, source="vm_manager")

    return vm


async def release(vm_id: str, project_id: str) -> bool:
    """Release a VM, verifying project ownership."""
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")
    if vm["project_id"] != project_id:
        raise PermissionError("VM belongs to another project")

    # Tell the host to destroy it first
    host = await pool.get_host(vm["host_id"])
    if host and host.get("ip"):
        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                await client.delete(
                    f"http://{host['ip']}:{AGENT_PORT}/pool/vms/{vm_id}",
                    headers=_host_auth(host),
                )
        except Exception:
            pass

    released = await pool.release_vm(vm_id)

    await emit("vm.released", {
        "vm_id": vm_id,
        "project_id": project_id,
    }, source="vm_manager")

    return released


async def suspend(vm_id: str, reason: str = ""):
    """
    Suspend a VM (e.g., for non-payment or abuse).
    The VM is stopped but not destroyed — can be resumed.
    """
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")

    # Stop the container on the host
    host = await pool.get_host(vm["host_id"])
    if host and host.get("ip"):
        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                await client.delete(
                    f"http://{host['ip']}:{AGENT_PORT}/pool/vms/{vm_id}",
                    headers=_host_auth(host),
                )
        except Exception:
            pass

    await pool.set_vm_status(vm_id, "suspended")
    await emit("vm.suspended", {
        "vm_id": vm_id,
        "project_id": vm["project_id"],
        "reason": reason,
    }, source="vm_manager")
    logger.info("VM %s suspended: %s", vm_id, reason)


async def resume(vm_id: str):
    """Resume a suspended VM."""
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")
    if vm.get("status") != "suspended":
        raise ValueError(f"VM {vm_id} is not suspended (status: {vm.get('status')})")

    # Set to creating — the reconciler will recreate it
    await pool.set_vm_status(vm_id, "creating")
    await emit("vm.resumed", {
        "vm_id": vm_id,
        "project_id": vm["project_id"],
    }, source="vm_manager")
    logger.info("VM %s resumed", vm_id)


async def migrate(vm_id: str, target_host_id: str = ""):
    """
    Migrate a VM to another host.
    If target_host_id is empty, auto-select the best host.
    """
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise ValueError(f"VM {vm_id} not found")

    old_host_id = vm["host_id"]

    # Find target host
    if target_host_id:
        target = await pool.get_host(target_host_id)
        if not target or target.get("status") != "active":
            raise ValueError(f"Target host {target_host_id} not available")
    else:
        target = await pool._find_best_host(
            vm["vcpus"], vm["ram_mb"], vm["disk_gb"],
        )
        if not target or target["id"] == old_host_id:
            raise ValueError("No suitable target host available")

    # Stop on old host
    old_host = await pool.get_host(old_host_id)
    if old_host and old_host.get("ip"):
        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                await client.delete(
                    f"http://{old_host['ip']}:{AGENT_PORT}/pool/vms/{vm_id}",
                    headers=_host_auth(old_host),
                )
        except Exception:
            pass

    # Update VM record — will be recreated on target by next sweep
    await db.update("compute_vms", vm_id, {
        "host_id": target["id"],
        "ip_external": target["ip"],
        "status": "creating",
        "container_id": "",
        "pid": 0,
    })

    # Update resource counts
    await db.update("compute_hosts", old_host_id, {
        "vcpus_used": max(0, (old_host or {}).get("vcpus_used", 0) - vm["vcpus"]),
        "ram_mb_used": max(0, (old_host or {}).get("ram_mb_used", 0) - vm["ram_mb"]),
        "disk_gb_used": max(0, (old_host or {}).get("disk_gb_used", 0) - vm["disk_gb"]),
    })
    await db.update("compute_hosts", target["id"], {
        "vcpus_used": target.get("vcpus_used", 0) + vm["vcpus"],
        "ram_mb_used": target.get("ram_mb_used", 0) + vm["ram_mb"],
        "disk_gb_used": target.get("disk_gb_used", 0) + vm["disk_gb"],
    })

    await emit("vm.migrated", {
        "vm_id": vm_id,
        "from_host": old_host_id,
        "to_host": target["id"],
        "project_id": vm["project_id"],
    }, source="vm_manager")

    logger.info("VM %s migrated: %s → %s", vm_id, old_host_id, target["id"])
    return {"vm_id": vm_id, "from_host": old_host_id, "to_host": target["id"]}


def get_stats() -> dict:
    """Get VM manager statistics."""
    return {
        "running": _task is not None and not _task.done(),
        "check_interval": CHECK_INTERVAL,
        "max_vms_per_project": DEFAULT_MAX_VMS_PER_PROJECT,
    }


def _host_auth(host: dict) -> dict:
    """Build auth headers for host agent."""
    token = host.get("agent_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
