"""
Instance service management — tracks and controls services running on instances.

The agent's supervisor manages actual process lifecycle. This module:
1. Polls supervisor status from agents and persists to DB
2. Provides CRUD for viewing service state
3. Proxies control commands (restart, stop, apply) to the agent
"""

import json
import logging
import secrets
from datetime import datetime, timezone

import httpx

from nso.shared import db
from nso.shared.errors import NotFoundError, NsoError, ProviderError
from nso.engine.compute.service import get_instance, _agent_login, _ipv4_client

logger = logging.getLogger("nso.compute.services")

AGENT_TIMEOUT = 15


def _gen_id() -> str:
    return f"isvc_{secrets.token_hex(8)}"


# ── Read operations ──


async def list_services(project_id: str, instance_id: str) -> list[dict]:
    """List all services for an instance."""
    await get_instance(project_id, instance_id)
    return await db.fetch_all(
        "instance_services",
        order_by="name ASC",
        instance_id=instance_id,
    )


async def get_service(project_id: str, instance_id: str, service_name: str) -> dict:
    """Get a single service by name."""
    await get_instance(project_id, instance_id)
    svc = await db.fetch_one("instance_services", instance_id=instance_id, name=service_name)
    if not svc:
        raise NotFoundError("Service", f"{instance_id}/{service_name}")
    return svc


async def get_live_status(project_id: str, instance_id: str) -> dict:
    """Fetch live supervisor status directly from the agent."""
    inst = await get_instance(project_id, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise ProviderError("agent", "Instance has no IP address")

    token = await _agent_login(ip)
    async with _ipv4_client(AGENT_TIMEOUT) as client:
        resp = await client.get(
            f"http://{ip}:8081/supervisor/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise ProviderError("agent", f"Supervisor status failed ({resp.status_code})")
        return resp.json()


# ── Control operations (proxied to agent) ──


async def restart_service(project_id: str, instance_id: str, service_name: str) -> dict:
    """Restart a service by removing and re-adding it to desired state."""
    inst = await get_instance(project_id, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise ProviderError("agent", "Instance has no IP address")

    token = await _agent_login(ip)

    # Get current desired spec from supervisor
    async with _ipv4_client(AGENT_TIMEOUT) as client:
        resp = await client.get(
            f"http://{ip}:8081/supervisor/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise ProviderError("agent", f"Cannot get supervisor status ({resp.status_code})")
        status = resp.json()

    desired = status.get("desired", {})
    if service_name not in desired:
        raise NotFoundError("Service", service_name)

    # Stop then re-apply (supervisor will restart it)
    async with _ipv4_client(AGENT_TIMEOUT) as client:
        # Stop the service
        resp = await client.post(
            f"http://{ip}:8081/supervisor/stop/{service_name}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code not in (200, 404):
            raise ProviderError("agent", f"Stop failed ({resp.status_code}): {resp.text}")

    # Re-apply with same specs (will start it again)
    async with _ipv4_client(AGENT_TIMEOUT + 10) as client:
        resp = await client.post(
            f"http://{ip}:8081/supervisor/apply",
            headers={"Authorization": f"Bearer {token}"},
            json={"processes": list(desired.values())},
        )
        if resp.status_code != 200:
            raise ProviderError("agent", f"Apply failed ({resp.status_code}): {resp.text}")

    logger.info("Restarted service %s on instance %s", service_name, instance_id)
    return {"restarted": True, "service": service_name, "instance_id": instance_id}


async def stop_service(project_id: str, instance_id: str, service_name: str) -> dict:
    """Stop a service on an instance (removes from desired state)."""
    inst = await get_instance(project_id, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise ProviderError("agent", "Instance has no IP address")

    token = await _agent_login(ip)
    async with _ipv4_client(AGENT_TIMEOUT) as client:
        resp = await client.post(
            f"http://{ip}:8081/supervisor/stop/{service_name}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            raise NotFoundError("Service", service_name)
        if resp.status_code != 200:
            raise ProviderError("agent", f"Stop failed ({resp.status_code}): {resp.text}")

    logger.info("Stopped service %s on instance %s", service_name, instance_id)
    return {"stopped": True, "service": service_name, "instance_id": instance_id}


async def apply_services(project_id: str, instance_id: str, specs: list[dict]) -> dict:
    """Apply a set of service specs to an instance's supervisor."""
    inst = await get_instance(project_id, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise ProviderError("agent", "Instance has no IP address")

    token = await _agent_login(ip)
    async with _ipv4_client(AGENT_TIMEOUT + 10) as client:
        resp = await client.post(
            f"http://{ip}:8081/supervisor/apply",
            headers={"Authorization": f"Bearer {token}"},
            json={"processes": specs},
        )
        if resp.status_code != 200:
            raise ProviderError("agent", f"Apply failed ({resp.status_code}): {resp.text}")
        data = resp.json()

    logger.info("Applied %d services to instance %s", len(specs), instance_id)
    return data


# ── Sync: poll agent and persist to DB ──


async def sync_services_from_agent(instance_id: str, ip: str) -> int:
    """
    Fetch supervisor status from agent and upsert into instance_services table.
    Returns number of services synced.
    """
    try:
        token = await _agent_login(ip)
    except Exception:
        return 0

    try:
        async with _ipv4_client(AGENT_TIMEOUT) as client:
            resp = await client.get(
                f"http://{ip}:8081/supervisor/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                return 0
            status = resp.json()
    except Exception:
        return 0

    processes = status.get("processes", {})
    desired = status.get("desired", {})
    now = datetime.now(timezone.utc).isoformat()
    synced = 0

    # Get all service names from both actual and desired
    all_names = set(processes.keys()) | set(desired.keys())

    for name in all_names:
        proc = processes.get(name, {})
        spec = desired.get(name, {})

        svc_data = {
            "instance_id": instance_id,
            "name": name,
            "status": proc.get("status", "pending"),
            "pid": proc.get("pid", 0),
            "port": proc.get("port", 0) or spec.get("port", 0),
            "version": proc.get("version", "") or spec.get("version", ""),
            "command": spec.get("command", ""),
            "working_dir": spec.get("working_dir", "/opt/app"),
            "health_path": spec.get("health_path", ""),
            "restart_policy": spec.get("restart_policy", "always"),
            "restart_count": proc.get("restart_count", 0),
            "cpu_percent": proc.get("cpu_percent", 0),
            "rss_mb": proc.get("rss_mb", 0),
            "uptime": proc.get("uptime", 0),
            "consecutive_failures": proc.get("consecutive_failures", 0),
            "error": proc.get("error", ""),
            "depends_on": spec.get("depends_on", []),
            "collected_at": now,
            "updated_at": now,
        }

        existing = await db.fetch_one("instance_services", instance_id=instance_id, name=name)
        if existing:
            await db.update("instance_services", existing["id"], svc_data)
        else:
            svc_data["id"] = _gen_id()
            svc_data["created_at"] = now
            await db.insert("instance_services", svc_data)
        synced += 1

    # Remove services that no longer exist on the agent
    db_services = await db.fetch_all("instance_services", instance_id=instance_id)
    for db_svc in db_services:
        if db_svc["name"] not in all_names:
            await db.delete("instance_services", db_svc["id"])

    return synced


async def sync_replicas_from_agent(instance_id: str, ip: str) -> int:
    """
    After syncing instance_services, update service_replicas for any
    registered services that match by name. This bridges the gap between
    the raw agent state and the service registry.
    """
    # Get all instance_services for this instance
    agent_services = await db.fetch_all("instance_services", instance_id=instance_id)
    if not agent_services:
        return 0

    # Get all service_replicas that reference this instance
    replicas = await db.fetch_all("service_replicas", instance_id=instance_id)
    replica_by_service = {r["service_id"]: r for r in replicas}

    # Get all registered services to match by name
    all_registries = await db.fetch_all("service_registry")
    registry_by_name = {}
    for svc in all_registries:
        registry_by_name[svc["name"]] = svc

    now = datetime.now(timezone.utc).isoformat()
    synced = 0

    for agent_svc in agent_services:
        name = agent_svc["name"]
        reg = registry_by_name.get(name)
        if not reg:
            continue  # Not a registered service

        service_id = reg["id"]
        replica = replica_by_service.get(service_id)

        update_data = {
            "status": agent_svc.get("status", "pending"),
            "pid": agent_svc.get("pid", 0),
            "port": agent_svc.get("port", 0),
            "version": agent_svc.get("version", ""),
            "cpu_percent": agent_svc.get("cpu_percent", 0),
            "rss_mb": agent_svc.get("rss_mb", 0),
            "uptime": agent_svc.get("uptime", 0),
            "error": agent_svc.get("error", ""),
            "collected_at": now,
            "updated_at": now,
        }

        if replica:
            await db.update("service_replicas", replica["id"], update_data)
        else:
            import secrets as _secrets
            update_data["id"] = f"rep_{_secrets.token_hex(8)}"
            update_data["service_id"] = service_id
            update_data["instance_id"] = instance_id
            update_data["created_at"] = now
            await db.insert("service_replicas", update_data)

        synced += 1

    return synced
