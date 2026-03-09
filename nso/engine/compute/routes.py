from fastapi import APIRouter, Body, Depends, HTTPException

from nso.shared.models import CreateInstanceRequest, InstanceExecRequest
from nso.engine.compute import service as im
from nso.engine.compute import supervisor_sync as svc_mgr
from nso.shared.errors import NsoError
from nso.shared.deps import require_project, require_project_owner

router = APIRouter()


@router.post("")
async def create_instance(req: CreateInstanceRequest, project_id: str = Depends(require_project_owner)):
    try:
        instance = await im.create_instance(project_id, req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {
        "instance": {
            "id": instance.id,
            "type": instance.type.value,
            "state": instance.state.value,
            "region": instance.region,
            "plan": instance.plan,
            "domain": instance.domain,
        },
        "message": "Machine is being provisioned. Poll the endpoint until state is 'ready'.",
        "poll_url": f"/api/projects/{project_id}/instances/{instance.id}",
    }


@router.get("")
async def list_instances(project_id: str = Depends(require_project), metrics: bool = False):
    instances = await im.list_instances(project_id)
    result = {"instances": instances}
    if metrics:
        from nso.engine.compute.metrics import get_project_metrics
        result["metrics"] = await get_project_metrics(project_id)
    return result


@router.get("/{instance_id}")
async def get_instance(instance_id: str, project_id: str = Depends(require_project)):
    try:
        inst = await im.get_instance(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"instance": inst}


@router.delete("/{instance_id}")
async def delete_instance(instance_id: str, project_id: str = Depends(require_project_owner)):
    try:
        await im.delete_instance(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True, "instance_id": instance_id}


@router.post("/{instance_id}/stop")
async def stop_instance(instance_id: str, project_id: str = Depends(require_project_owner)):
    try:
        await im.stop_instance(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"stopped": True}


@router.post("/{instance_id}/start")
async def start_instance(instance_id: str, project_id: str = Depends(require_project_owner)):
    try:
        await im.start_instance(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"started": True}


@router.post("/{instance_id}/exec")
async def exec_on_instance(instance_id: str, req: InstanceExecRequest, project_id: str = Depends(require_project_owner)):
    try:
        output, exit_code = await im.exec_on_instance(project_id, instance_id, req.command, req.timeout)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"output": output, "exit_code": exit_code}


@router.get("/{instance_id}/metrics")
async def get_instance_metrics(instance_id: str, project_id: str = Depends(require_project)):
    from nso.engine.compute.metrics import get_instance_metrics as _get
    result = await _get(project_id, instance_id)
    if not result:
        raise HTTPException(404, "Machine not found")
    return result


@router.get("/{instance_id}/logs")
async def get_instance_logs(instance_id: str, project_id: str = Depends(require_project), tail: int = 100):
    from nso.engine.deploy.service import get_deploy_logs
    try:
        await im.get_instance(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    logs = await get_deploy_logs(instance_id, limit=tail)
    return {"logs": logs}


# ── Service management routes ──


@router.get("/{instance_id}/services")
async def list_services(instance_id: str, project_id: str = Depends(require_project)):
    """List all services running on a machine."""
    try:
        services = await svc_mgr.list_services(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"services": services, "instance_id": instance_id}


@router.get("/{instance_id}/services/live")
async def get_live_services(instance_id: str, project_id: str = Depends(require_project)):
    """Fetch live supervisor status directly from the agent."""
    try:
        status = await svc_mgr.get_live_status(project_id, instance_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"supervisor": status, "instance_id": instance_id}


@router.get("/{instance_id}/services/{service_name}")
async def get_service(instance_id: str, service_name: str, project_id: str = Depends(require_project)):
    """Get details for a specific service."""
    try:
        service = await svc_mgr.get_service(project_id, instance_id, service_name)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"service": service}


@router.post("/{instance_id}/services/{service_name}/restart")
async def restart_service(instance_id: str, service_name: str, project_id: str = Depends(require_project_owner)):
    """Restart a service on a machine."""
    try:
        result = await svc_mgr.restart_service(project_id, instance_id, service_name)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/{instance_id}/services/{service_name}/stop")
async def stop_service(instance_id: str, service_name: str, project_id: str = Depends(require_project_owner)):
    """Stop a service on a machine."""
    try:
        result = await svc_mgr.stop_service(project_id, instance_id, service_name)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/{instance_id}/services/apply")
async def apply_services(
    instance_id: str,
    specs: list[dict] = Body(..., embed=True),
    project_id: str = Depends(require_project_owner),
):
    """Apply a set of service specs to the machine's supervisor."""
    try:
        result = await svc_mgr.apply_services(project_id, instance_id, specs)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result
