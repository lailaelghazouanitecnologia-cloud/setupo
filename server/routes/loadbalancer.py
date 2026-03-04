"""
Load balancer admin routes — manage pools, backends, rules, health, nginx config.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from server.deps import require_admin
from server.core.errors import NsoError
from server.core.loadbalancer.models import (
    LBPool, Backend, LBRule, LBOverview,
    CreatePoolRequest, UpdatePoolRequest,
    AddBackendRequest, UpdateBackendRequest,
    CreateRuleRequest, BackendStatus,
)
from server.core.loadbalancer import pool_manager
from server.core.loadbalancer.nginx_gen import generate_full_config, generate_upstream_config

logger = logging.getLogger("nso.routes.lb")

router = APIRouter()


# ── Overview ──────────────────────────────────────────────

@router.get("/overview", response_model=LBOverview)
async def lb_overview(_admin=Depends(require_admin)):
    """Full load balancer overview."""
    pools = await pool_manager.list_pools()
    all_backends = []
    for p in pools:
        all_backends.extend(p.backends)

    healthy = len([b for b in all_backends if b.status == BackendStatus.HEALTHY])
    unhealthy = len([b for b in all_backends if b.status == BackendStatus.UNHEALTHY])
    total_reqs = sum(b.total_requests for b in all_backends)

    return LBOverview(
        total_pools=len(pools),
        active_pools=len([p for p in pools if p.active]),
        total_backends=len(all_backends),
        healthy_backends=healthy,
        unhealthy_backends=unhealthy,
        total_rules=len(await pool_manager.list_rules()),
        total_requests=total_reqs,
        pools=pools,
    )


# ── Pools ─────────────────────────────────────────────────

@router.get("/pools", response_model=list[LBPool])
async def list_pools(
    project_id: str | None = Query(None),
    _admin=Depends(require_admin),
):
    return await pool_manager.list_pools(project_id=project_id)


@router.post("/pools", response_model=LBPool)
async def create_pool(req: CreatePoolRequest, _admin=Depends(require_admin)):
    try:
        return await pool_manager.create_pool(req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/pools/{pool_id}", response_model=LBPool)
async def get_pool(pool_id: str, _admin=Depends(require_admin)):
    try:
        return await pool_manager.get_pool(pool_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.patch("/pools/{pool_id}", response_model=LBPool)
async def update_pool(pool_id: str, req: UpdatePoolRequest, _admin=Depends(require_admin)):
    try:
        return await pool_manager.update_pool(pool_id, req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/pools/{pool_id}")
async def delete_pool(pool_id: str, _admin=Depends(require_admin)):
    try:
        await pool_manager.delete_pool(pool_id)
        return {"ok": True}
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


# ── Backends ──────────────────────────────────────────────

@router.get("/pools/{pool_id}/backends", response_model=list[Backend])
async def list_backends(pool_id: str, _admin=Depends(require_admin)):
    try:
        return await pool_manager.list_backends(pool_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/pools/{pool_id}/backends", response_model=Backend)
async def add_backend(pool_id: str, req: AddBackendRequest, _admin=Depends(require_admin)):
    try:
        return await pool_manager.add_backend(pool_id, req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.patch("/backends/{backend_id}", response_model=Backend)
async def update_backend(backend_id: str, req: UpdateBackendRequest, _admin=Depends(require_admin)):
    try:
        return await pool_manager.update_backend(backend_id, req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/backends/{backend_id}")
async def remove_backend(backend_id: str, _admin=Depends(require_admin)):
    try:
        await pool_manager.remove_backend(backend_id)
        return {"ok": True}
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


# ── Rules ─────────────────────────────────────────────────

@router.get("/rules", response_model=list[LBRule])
async def list_rules(
    pool_id: str | None = Query(None),
    _admin=Depends(require_admin),
):
    return await pool_manager.list_rules(pool_id=pool_id)


@router.post("/rules", response_model=LBRule)
async def create_rule(req: CreateRuleRequest, _admin=Depends(require_admin)):
    try:
        return await pool_manager.create_rule(req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, _admin=Depends(require_admin)):
    try:
        await pool_manager.delete_rule(rule_id)
        return {"ok": True}
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


# ── Nginx Config Generation ──────────────────────────────

@router.get("/nginx/config", response_class=PlainTextResponse)
async def get_nginx_config(_admin=Depends(require_admin)):
    """Generate nginx upstream + location config from current LB state."""
    return await generate_full_config()


@router.get("/nginx/upstreams", response_class=PlainTextResponse)
async def get_nginx_upstreams(_admin=Depends(require_admin)):
    """Generate only the upstream blocks."""
    return await generate_upstream_config()
