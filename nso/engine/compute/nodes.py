"""
Compute nodes — unified abstraction over VPS instances, pool nodes, and mesh devices.

A compute_node is any machine where services can run. It can be:
- A Vultr VPS (provider=vultr) — managed, always-on, costs money
- A mesh device / PC (provider=mesh) — user-owned, connects via reverse SSH tunnel
- A manually registered node (provider=manual) — user manages connectivity
"""

import logging
import secrets
from datetime import datetime, timezone

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, ValidationError

logger = logging.getLogger("nso.compute.nodes")

VALID_PROVIDERS = {"vultr", "mesh", "manual"}
VALID_ROLES = {"general", "compute", "build", "gateway", "storage"}
VALID_STATUSES = {"pending", "provisioning", "online", "offline", "draining", "maintenance"}

# Plan → resource mapping for auto-detection
PLAN_RESOURCES = {
    "vc2-1c-1gb": (1, 1024, 25),
    "vc2-1c-2gb": (1, 2048, 55),
    "vc2-2c-4gb": (2, 4096, 80),
    "vc2-4c-8gb": (4, 8192, 160),
    "vc2-6c-16gb": (6, 16384, 320),
    "vc2-8c-32gb": (8, 32768, 640),
}


def _gen_id() -> str:
    return f"node_{secrets.token_hex(8)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_node_replicas(node: dict) -> list[dict]:
    """Get all replicas for a node, checking both node_id and instance_id."""
    replicas = await db.fetch_all("service_replicas", instance_id=node["id"])
    # Also check legacy replicas stored by the node's backing instance_id
    if node.get("instance_id"):
        legacy = await db.fetch_all("service_replicas", instance_id=node["instance_id"])
        existing_ids = {r["id"] for r in replicas}
        replicas.extend(r for r in legacy if r["id"] not in existing_ids)
    return replicas


# ── CRUD ──


async def register_node(project_id: str, label: str, **kwargs) -> dict:
    """Register a compute node in the project."""
    provider = kwargs.get("provider", "vultr")
    if provider not in VALID_PROVIDERS:
        raise ValidationError(f"Invalid provider: {provider}. Must be one of: {VALID_PROVIDERS}")

    role = kwargs.get("role", "general")
    if role not in VALID_ROLES:
        raise ValidationError(f"Invalid role: {role}. Must be one of: {VALID_ROLES}")

    node_id = _gen_id()
    now = _now()

    data = {
        "id": node_id,
        "project_id": project_id,
        "label": label,
        "provider": provider,
        "created_at": now,
        "updated_at": now,
    }

    for field in (
        "instance_id", "ip", "agent_port", "role", "status",
        "cpu_cores", "mem_total_mb", "disk_total_gb",
        "max_services", "buffer_cpu_percent", "buffer_mem_percent",
        "reserved_for", "tags", "capabilities", "labels",
        "tunnel_config", "os_info", "agent_version", "metadata",
    ):
        if field in kwargs and kwargs[field] is not None:
            data[field] = kwargs[field]

    await db.insert("compute_nodes", data)
    logger.info("Registered node %s (%s/%s) for project %s", node_id, provider, label, project_id)

    return await db.fetch_one("compute_nodes", id=node_id)


async def get_node(project_id: str, node_id: str) -> dict:
    """Get a compute node by ID."""
    node = await db.fetch_one("compute_nodes", id=node_id)
    if not node or node["project_id"] != project_id:
        raise NotFoundError("Node", node_id)
    return node


async def list_nodes(project_id: str, status: str = "", role: str = "") -> list[dict]:
    """List all compute nodes for a project, optionally filtered."""
    filters = {"project_id": project_id}
    if status:
        filters["status"] = status
    if role:
        filters["role"] = role
    return await db.fetch_all("compute_nodes", order_by="created_at ASC", **filters)


async def update_node(project_id: str, node_id: str, **updates) -> dict:
    """Update a node's configuration."""
    node = await get_node(project_id, node_id)

    allowed = {
        "label", "role", "status", "ip", "agent_port",
        "cpu_cores", "mem_total_mb", "disk_total_gb",
        "max_services", "buffer_cpu_percent", "buffer_mem_percent",
        "reserved_for", "tags", "capabilities", "labels",
        "tunnel_config", "metadata", "agent_version", "os_info",
    }

    data = {k: v for k, v in updates.items() if k in allowed}
    if not data:
        return node

    if "role" in data and data["role"] not in VALID_ROLES:
        raise ValidationError(f"Invalid role: {data['role']}")

    data["updated_at"] = _now()
    await db.update("compute_nodes", node_id, data)
    return await db.fetch_one("compute_nodes", id=node_id)


async def delete_node(project_id: str, node_id: str):
    """Delete a compute node."""
    node = await get_node(project_id, node_id)

    # Check no active replicas on this node (by node_id or by instance_id)
    replicas = await _get_node_replicas(node)
    active = [r for r in replicas if r.get("status") not in ("stopped", "failed", "destroyed")]
    if active:
        raise ConflictError(f"Node has {len(active)} active replicas. Stop services first.")

    await db.delete("compute_nodes", node_id)
    logger.info("Deleted node %s", node_id)


# ── Node operations ──


async def drain_node(project_id: str, node_id: str) -> dict:
    """Mark node as draining — no new services, existing finish gracefully."""
    node = await get_node(project_id, node_id)
    if node["status"] == "draining":
        return node
    await db.update("compute_nodes", node_id, {"status": "draining", "updated_at": _now()})
    logger.info("Draining node %s", node_id)
    return await db.fetch_one("compute_nodes", id=node_id)


async def cordon_node(project_id: str, node_id: str) -> dict:
    """Mark node as maintenance — no new assignments, no eviction."""
    await get_node(project_id, node_id)
    await db.update("compute_nodes", node_id, {"status": "maintenance", "updated_at": _now()})
    return await db.fetch_one("compute_nodes", id=node_id)


async def uncordon_node(project_id: str, node_id: str) -> dict:
    """Restore node to online status."""
    await get_node(project_id, node_id)
    await db.update("compute_nodes", node_id, {"status": "online", "updated_at": _now()})
    return await db.fetch_one("compute_nodes", id=node_id)


async def reserve_node(project_id: str, node_id: str, service_id: str) -> dict:
    """Reserve a node exclusively for a service (dedicated placement)."""
    node = await get_node(project_id, node_id)
    if node["reserved_for"] and node["reserved_for"] != service_id:
        raise ConflictError(f"Node already reserved for service {node['reserved_for']}")
    await db.update("compute_nodes", node_id, {"reserved_for": service_id, "updated_at": _now()})
    return await db.fetch_one("compute_nodes", id=node_id)


async def release_node(project_id: str, node_id: str) -> dict:
    """Release a node from dedicated reservation."""
    await get_node(project_id, node_id)
    await db.update("compute_nodes", node_id, {"reserved_for": None, "updated_at": _now()})
    return await db.fetch_one("compute_nodes", id=node_id)


async def update_node_metrics(node_id: str, cpu: float, mem: float, disk: float, load: float):
    """Update real-time metrics from agent heartbeat."""
    await db.update("compute_nodes", node_id, {
        "cpu_used_percent": cpu,
        "mem_used_percent": mem,
        "disk_used_percent": disk,
        "load_1m": load,
        "agent_reachable": 1,
        "last_heartbeat": _now(),
        "updated_at": _now(),
    })


async def mark_node_offline(node_id: str):
    """Mark a node as offline (missed heartbeats)."""
    await db.update("compute_nodes", node_id, {
        "status": "offline",
        "agent_reachable": 0,
        "updated_at": _now(),
    })


# ── Resource accounting ──


async def get_available_resources(node_id: str) -> dict:
    """Calculate available resources on a node (total - allocated - buffer)."""
    node = await db.fetch_one("compute_nodes", id=node_id)
    if not node:
        return {"cpu": 0, "mem_mb": 0}

    cpu_cores = node.get("cpu_cores") or 1
    mem_total = node.get("mem_total_mb") or 1024

    buffer_cpu = cpu_cores * (node.get("buffer_cpu_percent", 10) / 100)
    buffer_mem = mem_total * (node.get("buffer_mem_percent", 10) / 100)

    cpu_avail = cpu_cores - buffer_cpu - (node.get("cpu_allocated", 0) or 0)
    mem_avail = mem_total - buffer_mem - (node.get("mem_allocated_mb", 0) or 0)

    return {
        "cpu_available": max(0, round(cpu_avail, 2)),
        "mem_available_mb": max(0, int(mem_avail)),
        "cpu_total": cpu_cores,
        "mem_total_mb": mem_total,
        "cpu_allocated": node.get("cpu_allocated", 0),
        "mem_allocated_mb": node.get("mem_allocated_mb", 0),
        "cpu_used_percent": node.get("cpu_used_percent", 0),
        "mem_used_percent": node.get("mem_used_percent", 0),
    }


async def recalculate_allocated(node_id: str):
    """Recalculate allocated resources from active service replicas."""
    node = await db.fetch_one("compute_nodes", id=node_id)
    replicas = await _get_node_replicas(node) if node else []
    active_replicas = [r for r in replicas if r.get("status") not in ("stopped", "failed", "destroyed")]

    total_cpu = 0.0
    total_mem = 0
    for replica in active_replicas:
        svc = await db.fetch_one("service_registry", id=replica["service_id"])
        if svc:
            total_cpu += svc.get("cpu_request", 0) or 0
            total_mem += svc.get("mem_request_mb", 0) or 0

    await db.update("compute_nodes", node_id, {
        "cpu_allocated": round(total_cpu, 2),
        "mem_allocated_mb": total_mem,
        "updated_at": _now(),
    })


# ── Auto-register from existing instances ──


async def auto_register_instance(project_id: str, instance_id: str) -> dict | None:
    """Auto-create a compute_node for an existing instance if not already registered."""
    existing = await db.fetch_one("compute_nodes", project_id=project_id, instance_id=instance_id)
    if existing:
        return existing

    inst = await db.fetch_one("instances", id=instance_id)
    if not inst or inst["project_id"] != project_id:
        return None

    # Detect resources from plan
    plan = inst.get("plan", "vc2-1c-1gb")
    cpu, mem, disk = PLAN_RESOURCES.get(plan, (1, 1024, 25))

    return await register_node(
        project_id,
        label=inst.get("label", "") or f"vps-{instance_id[:12]}",
        provider="vultr",
        instance_id=instance_id,
        ip=inst.get("ip", ""),
        role="general",
        status="online" if inst.get("state") in ("running", "ready", "active") else "pending",
        cpu_cores=cpu,
        mem_total_mb=mem,
        disk_total_gb=disk,
    )
