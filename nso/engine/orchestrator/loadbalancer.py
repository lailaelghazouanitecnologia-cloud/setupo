"""
Pool manager — CRUD for LB pools and backends.
"""
import logging
import secrets
from datetime import datetime

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, ValidationError
from nso.engine.orchestrator.lb_models import (
    LBPool, Backend, LBRule,
    CreatePoolRequest, UpdatePoolRequest,
    AddBackendRequest, UpdateBackendRequest,
    CreateRuleRequest, BackendStatus,
)

logger = logging.getLogger("nso.lb.pool")


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


# ── Pools ─────────────────────────────────────────────────

async def create_pool(req: CreatePoolRequest) -> LBPool:
    pool_id = _gen_id("lbpool")
    now = datetime.utcnow().isoformat()
    pool = LBPool(
        id=pool_id,
        name=req.name,
        project_id=req.project_id,
        algorithm=req.algorithm,
        health_check_path=req.health_check_path,
        health_check_interval=req.health_check_interval,
        health_check_timeout=req.health_check_timeout,
        max_fails=req.max_fails,
        sticky_sessions=req.sticky_sessions,
        created_at=now,
        updated_at=now,
    )
    await db.insert("lb_pools", {
        "id": pool.id,
        "name": pool.name,
        "project_id": pool.project_id or "",
        "algorithm": pool.algorithm.value,
        "health_check_path": pool.health_check_path,
        "health_check_interval": pool.health_check_interval,
        "health_check_timeout": pool.health_check_timeout,
        "max_fails": pool.max_fails,
        "sticky_sessions": int(pool.sticky_sessions),
        "sticky_cookie": pool.sticky_cookie,
        "active": 1,
        "created_at": now,
        "updated_at": now,
    })
    logger.info("LB pool created: %s (%s)", pool_id, req.name)
    return pool


async def get_pool(pool_id: str) -> LBPool:
    row = await db.fetch_one("lb_pools", id=pool_id)
    if not row:
        raise NotFoundError("LB pool", pool_id)
    backends = await list_backends(pool_id)
    return LBPool(**row, backends=backends)


async def list_pools(project_id: str | None = None) -> list[LBPool]:
    if project_id:
        rows = await db.fetch_all("lb_pools", order_by="created_at ASC", project_id=project_id)
    else:
        rows = await db.fetch_all("lb_pools", order_by="created_at ASC")
    pools = []
    for r in rows:
        backends = await list_backends(r["id"])
        pools.append(LBPool(**r, backends=backends))
    return pools


async def update_pool(pool_id: str, req: UpdatePoolRequest) -> LBPool:
    row = await db.fetch_one("lb_pools", id=pool_id)
    if not row:
        raise NotFoundError("LB pool", pool_id)

    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.algorithm is not None:
        updates["algorithm"] = req.algorithm.value
    if req.health_check_path is not None:
        updates["health_check_path"] = req.health_check_path
    if req.health_check_interval is not None:
        updates["health_check_interval"] = req.health_check_interval
    if req.health_check_timeout is not None:
        updates["health_check_timeout"] = req.health_check_timeout
    if req.max_fails is not None:
        updates["max_fails"] = req.max_fails
    if req.sticky_sessions is not None:
        updates["sticky_sessions"] = int(req.sticky_sessions)
    if req.active is not None:
        updates["active"] = int(req.active)

    if updates:
        updates["updated_at"] = datetime.utcnow().isoformat()
        await db.update("lb_pools", pool_id, updates)

    return await get_pool(pool_id)


async def delete_pool(pool_id: str):
    row = await db.fetch_one("lb_pools", id=pool_id)
    if not row:
        raise NotFoundError("LB pool", pool_id)
    # Delete backends and rules first
    await db.delete_where("lb_backends", pool_id=pool_id)
    await db.delete_where("lb_rules", pool_id=pool_id)
    await db.delete("lb_pools", pool_id)
    logger.info("LB pool deleted: %s", pool_id)


# ── Backends ──────────────────────────────────────────────

async def add_backend(pool_id: str, req: AddBackendRequest) -> Backend:
    pool_row = await db.fetch_one("lb_pools", id=pool_id)
    if not pool_row:
        raise NotFoundError("LB pool", pool_id)

    instance = await db.fetch_one("instances", id=req.instance_id)
    if not instance:
        raise NotFoundError("Instance", req.instance_id)

    # Check not already in this pool
    existing = await db.fetch_one("lb_backends", pool_id=pool_id, instance_id=req.instance_id)
    if existing:
        raise ConflictError(f"Instance {req.instance_id} already in pool {pool_id}")

    backend_id = _gen_id("lbbe")
    ip = instance.get("ip", "")
    if not ip:
        raise ValidationError("Instance has no IP address")

    backend = Backend(
        id=backend_id,
        pool_id=pool_id,
        instance_id=req.instance_id,
        ip=ip,
        port=req.port,
        weight=req.weight,
    )

    await db.insert("lb_backends", {
        "id": backend.id,
        "pool_id": pool_id,
        "instance_id": req.instance_id,
        "ip": ip,
        "port": req.port,
        "weight": req.weight,
        "status": BackendStatus.HEALTHY.value,
        "active_connections": 0,
        "total_requests": 0,
        "failed_health_checks": 0,
        "metadata": {},
        "created_at": backend.created_at,
    })

    logger.info("Backend added: %s → pool %s (ip=%s:%d)", backend_id, pool_id, ip, req.port)
    return backend


async def update_backend(backend_id: str, req: UpdateBackendRequest) -> Backend:
    row = await db.fetch_one("lb_backends", id=backend_id)
    if not row:
        raise NotFoundError("Backend", backend_id)

    updates = {}
    if req.weight is not None:
        if req.weight < 0:
            raise ValidationError("weight must be >= 0")
        updates["weight"] = req.weight
    if req.status is not None:
        updates["status"] = req.status.value
    if req.port is not None:
        updates["port"] = req.port

    if updates:
        await db.update("lb_backends", backend_id, updates)
        row.update(updates)

    return Backend(**row)


async def remove_backend(backend_id: str):
    row = await db.fetch_one("lb_backends", id=backend_id)
    if not row:
        raise NotFoundError("Backend", backend_id)
    await db.delete("lb_backends", backend_id)
    logger.info("Backend removed: %s", backend_id)


async def list_backends(pool_id: str) -> list[Backend]:
    rows = await db.fetch_all("lb_backends", order_by="created_at ASC", pool_id=pool_id)
    return [Backend(**r) for r in rows]


async def get_healthy_backends(pool_id: str) -> list[Backend]:
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM lb_backends WHERE pool_id = ? AND status = 'healthy' ORDER BY weight DESC",
        (pool_id,),
    )
    rows = await cursor.fetchall()
    return [Backend(**db.row_to_dict(r)) for r in rows]


# ── Rules ─────────────────────────────────────────────────

async def create_rule(req: CreateRuleRequest) -> LBRule:
    pool_row = await db.fetch_one("lb_pools", id=req.pool_id)
    if not pool_row:
        raise NotFoundError("LB pool", req.pool_id)

    rule_id = _gen_id("lbrule")
    rule = LBRule(
        id=rule_id,
        pool_id=req.pool_id,
        match_type=req.match_type,
        match_value=req.match_value,
        priority=req.priority,
        headers=req.headers,
    )

    await db.insert("lb_rules", {
        "id": rule.id,
        "pool_id": req.pool_id,
        "match_type": rule.match_type.value,
        "match_value": rule.match_value,
        "priority": rule.priority,
        "headers": rule.headers,
        "active": 1,
        "created_at": rule.created_at,
    })

    logger.info("LB rule created: %s (%s %s → %s)", rule_id, rule.match_type.value, rule.match_value, req.pool_id)
    return rule


async def list_rules(pool_id: str | None = None) -> list[LBRule]:
    if pool_id:
        rows = await db.fetch_all("lb_rules", order_by="priority DESC", pool_id=pool_id)
    else:
        rows = await db.fetch_all("lb_rules", order_by="priority DESC")
    return [LBRule(**r) for r in rows]


async def delete_rule(rule_id: str):
    row = await db.fetch_one("lb_rules", id=rule_id)
    if not row:
        raise NotFoundError("LB rule", rule_id)
    await db.delete("lb_rules", rule_id)
    logger.info("LB rule deleted: %s", rule_id)
