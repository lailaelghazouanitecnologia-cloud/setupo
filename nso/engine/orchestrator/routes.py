"""
Orchestrator admin routes — manage pool, builds, scaling.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from nso.shared.deps import require_admin
from nso.shared.errors import NsoError
from nso.engine.orchestrator.models import (
    PoolNode, RegisterNodeRequest, UpdateNodeRequest,
    BuildJob, SubmitBuildRequest, PoolOverview,
)
from nso.engine.orchestrator import pool, scheduler, scaler
from nso.engine.orchestrator.monitor import get_active_alerts, resolve_alert

logger = logging.getLogger("nso.routes.orchestrator")

router = APIRouter()


# ── Pool Management ────────────────────────────────────────

@router.get("/pool", response_model=list[PoolNode])
async def list_pool_nodes(
    role: str | None = Query(None),
    status: str | None = Query(None),
    _admin=Depends(require_admin),
):
    """List all pool nodes."""
    return await pool.list_nodes(role=role, status=status)


@router.post("/pool", response_model=PoolNode)
async def register_pool_node(
    req: RegisterNodeRequest,
    _admin=Depends(require_admin),
):
    """Register an instance as a pool node."""
    try:
        return await pool.register_node(req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/pool/{node_id}", response_model=PoolNode)
async def get_pool_node(
    node_id: str,
    _admin=Depends(require_admin),
):
    """Get node details."""
    try:
        return await pool.get_node(node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.patch("/pool/{node_id}", response_model=PoolNode)
async def update_pool_node(
    node_id: str,
    req: UpdateNodeRequest,
    _admin=Depends(require_admin),
):
    """Update node role, status, or config."""
    try:
        return await pool.update_node(node_id, req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/pool/{node_id}")
async def remove_pool_node(
    node_id: str,
    _admin=Depends(require_admin),
):
    """Remove node from pool."""
    try:
        await pool.remove_node(node_id)
        return {"ok": True}
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


# ── Build Queue ────────────────────────────────────────────

@router.get("/builds", response_model=list[BuildJob])
async def list_builds(
    status: str | None = Query(None),
    project_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    _admin=Depends(require_admin),
):
    """List build jobs."""
    return await scheduler.list_builds(status=status, project_id=project_id, limit=limit)


@router.post("/builds", response_model=BuildJob)
async def submit_build(
    req: SubmitBuildRequest,
    _admin=Depends(require_admin),
):
    """Submit a build job to the queue."""
    try:
        return await scheduler.submit_build(req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/builds/{build_id}", response_model=BuildJob)
async def get_build(
    build_id: str,
    _admin=Depends(require_admin),
):
    """Get build details."""
    try:
        return await scheduler.get_build(build_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/builds/{build_id}/cancel")
async def cancel_build(
    build_id: str,
    _admin=Depends(require_admin),
):
    """Cancel a queued or assigned build."""
    try:
        await scheduler.cancel_build(build_id)
        return {"ok": True}
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


# ── Metrics & Overview ─────────────────────────────────────

@router.get("/overview", response_model=PoolOverview)
async def pool_overview(
    _admin=Depends(require_admin),
):
    """Full pool overview with metrics and alerts."""
    return await scaler.get_pool_overview()


@router.get("/metrics")
async def pool_metrics(
    _admin=Depends(require_admin),
):
    """Get current metrics for all nodes."""
    nodes = await pool.list_nodes(status="active")
    return {
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "role": n.role.value,
                "ip": n.ip,
                "cpu_percent": n.cpu_percent,
                "mem_percent": n.mem_percent,
                "disk_percent": n.disk_percent,
                "active_builds": n.active_builds,
                "last_heartbeat": n.last_heartbeat,
            }
            for n in nodes
        ],
    }


@router.get("/recommendations")
async def get_recommendations(
    _admin=Depends(require_admin),
):
    """Get scaling recommendations."""
    return await scaler.get_recommendations()


@router.get("/alerts")
async def list_alerts(
    node_id: str | None = Query(None),
    _admin=Depends(require_admin),
):
    """List active alerts."""
    return await get_active_alerts(node_id)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert_endpoint(
    alert_id: str,
    _admin=Depends(require_admin),
):
    """Resolve an alert."""
    await resolve_alert(alert_id)
    return {"ok": True}


@router.get("/nodes/{node_id}/history")
async def node_build_history(
    node_id: str,
    hours: int = Query(24, le=168),
    _admin=Depends(require_admin),
):
    """Get recent build history for a node."""
    return await scaler.get_node_history(node_id, hours)


@router.post("/rebalance")
async def rebalance_pool(
    _admin=Depends(require_admin),
):
    """Process queued builds and try to assign them."""
    await scheduler._process_queue()
    return {"ok": True, "message": "Queue reprocessed"}
