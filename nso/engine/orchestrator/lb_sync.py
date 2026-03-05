"""
Sync — keep orchestrator pool nodes and LB backends in sync.

When a node is registered/removed from the orchestrator pool,
automatically update the LB backends to match.
"""
import logging
from datetime import datetime

from nso.shared import db
from nso.engine.orchestrator.lb_models import BackendStatus
from nso.engine.orchestrator import pool_manager

logger = logging.getLogger("nso.lb.sync")

# Default pool name for auto-synced nodes
DEFAULT_POOL_NAME = "nso-api-pool"
DEFAULT_POOL_PORT = 8000


async def ensure_default_pool() -> str:
    """Ensure the default API pool exists, return its ID."""
    pools = await pool_manager.list_pools()
    for p in pools:
        if p.name == DEFAULT_POOL_NAME:
            return p.id

    # Create default pool
    from nso.engine.orchestrator.lb_models import CreatePoolRequest, LBAlgorithm
    pool = await pool_manager.create_pool(CreatePoolRequest(
        name=DEFAULT_POOL_NAME,
        algorithm=LBAlgorithm.LEAST_CONNECTIONS,
        health_check_path="/api/health",
        health_check_interval=30,
        max_fails=3,
    ))
    logger.info("Default LB pool created: %s", pool.id)
    return pool.id


async def sync_node_to_lb(instance_id: str, ip: str, port: int = DEFAULT_POOL_PORT):
    """
    Add an orchestrator node as an LB backend (if not already present).
    Called when a node is registered to the orchestrator pool.
    """
    pool_id = await ensure_default_pool()

    # Check if already exists
    existing = await db.fetch_one("lb_backends", pool_id=pool_id, instance_id=instance_id)
    if existing:
        # Update IP if changed
        if existing.get("ip") != ip:
            await db.update("lb_backends", existing["id"], {"ip": ip})
            logger.info("LB backend %s IP updated: %s", existing["id"], ip)
        return

    # Add as backend
    from nso.engine.orchestrator.lb_models import AddBackendRequest
    await pool_manager.add_backend(pool_id, AddBackendRequest(
        instance_id=instance_id,
        port=port,
        weight=1,
    ))
    logger.info("Node %s synced to LB pool %s", instance_id, pool_id)


async def remove_node_from_lb(instance_id: str):
    """
    Remove an orchestrator node from all LB pools.
    Called when a node is removed from the orchestrator pool.
    """
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT id, pool_id FROM lb_backends WHERE instance_id = ?",
        (instance_id,),
    )
    rows = await cursor.fetchall()

    for row in rows:
        backend = db._row_to_dict(row)
        await pool_manager.remove_backend(backend["id"])
        logger.info("Removed LB backend %s (instance=%s) from pool %s",
                     backend["id"], instance_id, backend["pool_id"])


async def drain_node_in_lb(instance_id: str):
    """
    Set a node to draining status in all LB pools.
    No new connections will be routed to it.
    """
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT id FROM lb_backends WHERE instance_id = ?",
        (instance_id,),
    )
    rows = await cursor.fetchall()

    for row in rows:
        backend_id = db._row_to_dict(row)["id"]
        await db.update("lb_backends", backend_id, {
            "status": BackendStatus.DRAINING.value,
        })
    logger.info("Node %s set to draining in all LB pools", instance_id)


async def full_sync():
    """
    Full sync: ensure every active orchestrator node with role 'runner' or 'hybrid'
    is registered as an LB backend.
    """
    pool_id = await ensure_default_pool()

    # Get all runner/hybrid nodes
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM instance_pool WHERE status = 'active' AND role IN ('runner', 'hybrid')"
    )
    nodes = await cursor.fetchall()

    synced = 0
    for row in nodes:
        node = db._row_to_dict(row)
        ip = node.get("ip")
        if not ip:
            continue

        existing = await db.fetch_one("lb_backends", pool_id=pool_id, instance_id=node["instance_id"])
        if not existing:
            try:
                from nso.engine.orchestrator.lb_models import AddBackendRequest
                await pool_manager.add_backend(pool_id, AddBackendRequest(
                    instance_id=node["instance_id"],
                    port=DEFAULT_POOL_PORT,
                    weight=1,
                ))
                synced += 1
            except Exception as e:
                logger.warning("Failed to sync node %s: %s", node["id"], e)

    # Remove backends whose instances are no longer in the pool
    cursor = await d.execute(
        "SELECT lb.id, lb.instance_id FROM lb_backends lb "
        "LEFT JOIN instance_pool ip ON lb.instance_id = ip.instance_id "
        "WHERE lb.pool_id = ? AND (ip.id IS NULL OR ip.status = 'offline')",
        (pool_id,),
    )
    stale = await cursor.fetchall()
    for row in stale:
        stale_backend = db._row_to_dict(row)
        await pool_manager.remove_backend(stale_backend["id"])
        logger.info("Removed stale LB backend %s", stale_backend["id"])

    logger.info("Full LB sync complete: %d nodes added, %d stale removed", synced, len(stale))
    return {"synced": synced, "removed": len(stale)}
