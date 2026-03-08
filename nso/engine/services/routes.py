"""
Service management API routes.

All routes are project-scoped: /api/projects/{project_id}/services/...
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from nso.engine.services import service as svc
from nso.shared.errors import NsoError
from nso.shared.deps import require_project

router = APIRouter()


# ── Service Registry ──


@router.get("")
async def list_services(
    project_id: str = Depends(require_project),
    status: str = "",
    service_type: str = "",
):
    """List all services in a project."""
    try:
        services = await svc.list_services(project_id, status=status, service_type=service_type)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"services": services}


@router.post("")
async def create_service(
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Register a new service."""
    name = body.get("name")
    if not name:
        raise HTTPException(422, "name is required")
    kwargs = {k: v for k, v in body.items() if k != "name"}
    try:
        service = await svc.create_service(project_id, name, **kwargs)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"service": service}


@router.get("/{service_id}")
async def get_service(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Get service details."""
    try:
        service = await svc.get_service(project_id, service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"service": service}


@router.get("/{service_id}/overview")
async def get_service_overview(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Get full overview: service + replicas + scaling + connections + events."""
    try:
        overview = await svc.get_service_overview(project_id, service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return overview


@router.patch("/{service_id}")
async def update_service(
    service_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Update service configuration."""
    try:
        service = await svc.update_service(project_id, service_id, **body)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"service": service}


@router.delete("/{service_id}")
async def delete_service(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Delete a service and all its replicas."""
    try:
        await svc.delete_service(project_id, service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True, "service_id": service_id}


# ── Deploy ──


@router.post("/{service_id}/deploy")
async def deploy_service(
    service_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Deploy a service to instance(s). Body: {"instance_ids": ["inst_xxx", ...]}"""
    instance_ids = body.get("instance_ids", [])
    if not instance_ids:
        raise HTTPException(422, "instance_ids is required")
    try:
        result = await svc.deploy_service(project_id, service_id, instance_ids)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


# ── Start / Stop ──


@router.post("/{service_id}/start")
async def start_service(
    service_id: str,
    body: dict = Body(default={}),
    project_id: str = Depends(require_project),
):
    """Re-deploy a stopped service to its existing replicas' instances."""
    try:
        service = await svc.get_service(project_id, service_id)
        replicas = await svc.list_replicas(service_id)
        instance_ids = [r["instance_id"] for r in replicas]
        if not instance_ids:
            raise HTTPException(422, "No replicas found — use deploy first")
        result = await svc.deploy_service(project_id, service_id, instance_ids)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/{service_id}/stop")
async def stop_service(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Stop all replicas of a service across all instances."""
    try:
        from nso.engine.compute.supervisor_sync import stop_service as agent_stop

        service = await svc.get_service(project_id, service_id)
        replicas = await svc.list_replicas(service_id)
        stopped = 0
        failures = []
        for replica in replicas:
            try:
                await agent_stop(project_id, replica["instance_id"], service["name"])
                await svc.update_replica(replica["id"], status="stopped")
                stopped += 1
            except Exception as e:
                failures.append({"instance_id": replica["instance_id"], "error": str(e)})
        await svc.update_service(project_id, service_id, status="stopped")
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    result = {"stopped": stopped, "service_id": service_id}
    if failures:
        result["failures"] = failures
    return result


# ── Health ──


@router.get("/{service_id}/health")
async def get_service_health(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Get aggregated health status for a service."""
    try:
        await svc.get_service(project_id, service_id)
        replicas = await svc.list_replicas(service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    total = len(replicas)
    running = sum(1 for r in replicas if r.get("status") == "running")
    failed = sum(1 for r in replicas if r.get("status") in ("failed", "crashed"))
    pending = sum(1 for r in replicas if r.get("status") in ("pending", "starting"))

    if total == 0:
        health = "unknown"
    elif running == total:
        health = "healthy"
    elif running > 0:
        health = "degraded"
    elif failed > 0:
        health = "unhealthy"
    else:
        health = "starting"

    return {
        "service_id": service_id,
        "health": health,
        "replicas": {"total": total, "running": running, "failed": failed, "pending": pending},
    }


# ── Scaling ──


@router.post("/{service_id}/scale")
async def scale_service(
    service_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Set desired replica count. Body: {"replicas": 3}"""
    replicas = body.get("replicas")
    if replicas is None:
        raise HTTPException(422, "replicas is required")
    try:
        result = await svc.scale_service(project_id, service_id, int(replicas))
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.get("/{service_id}/scaling")
async def get_scaling(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Get scaling policy and current recommendation."""
    try:
        await svc.get_service(project_id, service_id)
        policy = await svc.get_scaling_policy(service_id)
        recommendation = await svc.evaluate_scaling(service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"policy": policy, "recommendation": recommendation}


@router.put("/{service_id}/scaling")
async def set_scaling(
    service_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Set scaling policy. Body: {"min_replicas": 1, "max_replicas": 5, "metric": "cpu", "target_value": 70}"""
    try:
        await svc.get_service(project_id, service_id)
        policy = await svc.set_scaling_policy(service_id, **body)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"policy": policy}


# ── Replicas ──


@router.get("/{service_id}/replicas")
async def list_replicas(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """List all replicas of a service."""
    try:
        await svc.get_service(project_id, service_id)
        replicas = await svc.list_replicas(service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"replicas": replicas, "count": len(replicas)}


# ── Events ──


@router.get("/{service_id}/events")
async def list_events(
    service_id: str,
    project_id: str = Depends(require_project),
    limit: int = 50,
):
    """List recent events for a service."""
    try:
        await svc.get_service(project_id, service_id)
        events = await svc.list_events(service_id, limit=limit)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"events": events}


# ── Dependencies / Connections ──


@router.get("/{service_id}/dependencies")
async def get_dependencies(
    service_id: str,
    project_id: str = Depends(require_project),
):
    """Get all resource connections for a service."""
    try:
        await svc.get_service(project_id, service_id)
        connections = await svc.list_connections(project_id, "service", service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"connections": connections}


# ── Resource Connections (project-level) ──


connections_router = APIRouter()


@connections_router.get("")
async def list_connections(
    project_id: str = Depends(require_project),
    resource_type: str = "",
    resource_id: str = "",
):
    """List all resource connections in a project."""
    try:
        connections = await svc.list_connections(project_id, resource_type, resource_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"connections": connections}


@connections_router.post("")
async def create_connection(
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Create a resource connection. Body: {"source_type": "service", "source_id": "svc_xxx", "target_type": "database", "target_id": "db_xxx", "config": {}}"""
    for field in ("source_type", "source_id", "target_type", "target_id"):
        if not body.get(field):
            raise HTTPException(422, f"{field} is required")
    try:
        connection = await svc.create_connection(
            project_id,
            body["source_type"], body["source_id"],
            body["target_type"], body["target_id"],
            config=body.get("config"),
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"connection": connection}


@connections_router.delete("/{connection_id}")
async def delete_connection(
    connection_id: str,
    project_id: str = Depends(require_project),
):
    """Delete a resource connection."""
    try:
        await svc.delete_connection(project_id, connection_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True, "connection_id": connection_id}
