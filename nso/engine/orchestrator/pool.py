"""
Pool manager — register, update, remove nodes from the orchestrator pool.
"""
import logging
import secrets
from datetime import datetime

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, ValidationError
from nso.engine.orchestrator.models import (
    PoolNode, RegisterNodeRequest, UpdateNodeRequest,
    NodeStatus, NodeRole,
)

logger = logging.getLogger("nso.orchestrator.pool")


def _gen_id() -> str:
    return f"node_{secrets.token_hex(8)}"


async def register_node(req: RegisterNodeRequest) -> PoolNode:
    """Register an instance as a pool node."""
    # Check instance exists
    instance = await db.fetch_one("instances", id=req.instance_id)
    if not instance:
        raise NotFoundError("Instance", req.instance_id)

    # Check not already registered
    existing = await db.fetch_one("instance_pool", instance_id=req.instance_id)
    if existing:
        raise ConflictError(f"Instance {req.instance_id} is already in the pool")

    node_id = _gen_id()
    node = PoolNode(
        id=node_id,
        instance_id=req.instance_id,
        label=req.label or instance.get("label", ""),
        role=req.role,
        status=NodeStatus.ACTIVE,
        ip=req.ip or instance.get("ip"),
        region=req.region,
        plan=req.plan,
        max_concurrent_builds=req.max_concurrent_builds,
    )

    await db.insert("instance_pool", {
        "id": node.id,
        "instance_id": node.instance_id,
        "label": node.label,
        "role": node.role.value,
        "status": node.status.value,
        "ip": node.ip,
        "region": node.region,
        "plan": node.plan,
        "max_concurrent_builds": node.max_concurrent_builds,
        "cpu_percent": 0.0,
        "mem_percent": 0.0,
        "disk_percent": 0.0,
        "active_builds": 0,
        "metadata": {},
        "created_at": node.created_at,
    })

    logger.info("Node registered: %s (instance=%s, role=%s)", node_id, req.instance_id, req.role.value)

    # Auto-sync to load balancer if runner/hybrid
    if req.role in (NodeRole.RUNNER, NodeRole.HYBRID) and node.ip:
        try:
            from nso.engine.orchestrator.lb_sync import sync_node_to_lb
            await sync_node_to_lb(req.instance_id, node.ip)
        except Exception as e:
            logger.warning("LB sync failed for %s: %s", req.instance_id, e)

    return node


async def update_node(node_id: str, req: UpdateNodeRequest) -> PoolNode:
    """Update node role, status, or config."""
    node = await db.fetch_one("instance_pool", id=node_id)
    if not node:
        raise NotFoundError("Pool node", node_id)

    updates = {}
    if req.label is not None:
        updates["label"] = req.label
    if req.role is not None:
        updates["role"] = req.role.value
    if req.status is not None:
        updates["status"] = req.status.value
    if req.max_concurrent_builds is not None:
        if req.max_concurrent_builds < 1:
            raise ValidationError("max_concurrent_builds must be >= 1")
        updates["max_concurrent_builds"] = req.max_concurrent_builds

    if updates:
        await db.update("instance_pool", node_id, updates)
        node.update(updates)

    logger.info("Node updated: %s → %s", node_id, list(updates.keys()))
    return PoolNode(**node)


async def remove_node(node_id: str):
    """Remove node from pool."""
    node = await db.fetch_one("instance_pool", id=node_id)
    if not node:
        raise NotFoundError("Pool node", node_id)

    # Check no active builds
    if node.get("active_builds", 0) > 0:
        raise ConflictError("Node has active builds. Set status to 'draining' first.")

    # Remove from load balancer
    instance_id = node.get("instance_id", "")
    try:
        from nso.engine.orchestrator.lb_sync import remove_node_from_lb
        await remove_node_from_lb(instance_id)
    except Exception as e:
        logger.warning("LB remove failed for %s: %s", instance_id, e)

    await db.delete("instance_pool", node_id)
    logger.info("Node removed: %s", node_id)


async def list_nodes(role: str | None = None, status: str | None = None) -> list[PoolNode]:
    """List all pool nodes, optionally filtered."""
    filters = {}
    if role:
        filters["role"] = role
    if status:
        filters["status"] = status

    rows = await db.fetch_all("instance_pool", order_by="created_at ASC", **filters)
    return [PoolNode(**r) for r in rows]


async def get_node(node_id: str) -> PoolNode:
    """Get a single node."""
    node = await db.fetch_one("instance_pool", id=node_id)
    if not node:
        raise NotFoundError("Pool node", node_id)
    return PoolNode(**node)


async def update_node_metrics(node_id: str, cpu: float, mem: float, disk: float, active_builds: int = 0):
    """Update node metrics (called by monitor)."""
    await db.update("instance_pool", node_id, {
        "cpu_percent": round(cpu, 1),
        "mem_percent": round(mem, 1),
        "disk_percent": round(disk, 1),
        "active_builds": active_builds,
        "last_heartbeat": datetime.utcnow().isoformat(),
    })


async def get_available_builders() -> list[PoolNode]:
    """Get builder/hybrid nodes that can accept builds."""
    d = await db.get_db()
    cursor = await d.execute(
        """SELECT * FROM instance_pool
           WHERE status = 'active'
             AND role IN ('builder', 'hybrid')
             AND active_builds < max_concurrent_builds
           ORDER BY cpu_percent ASC, active_builds ASC""",
    )
    rows = await cursor.fetchall()
    return [PoolNode(**db.row_to_dict(r)) for r in rows]
