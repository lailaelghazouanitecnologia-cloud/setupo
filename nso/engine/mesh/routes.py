from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from nso.shared.deps import require_project
from nso.shared.errors import NsoError
from nso.engine.mesh import service as mesh
from nso.engine.mesh.models import (
    RegisterDeviceRequest,
    UpdateDeviceRequest,
    ActivateDeviceRequest,
    DeviceExecRequest,
    CreateGroupRequest,
    UpdateGroupRequest,
    AddDevicesToGroupRequest,
    GroupExecRequest,
)
from nso.engine.mesh.bootstrap import generate_install_script

router = APIRouter()


# ── Devices ─────────────────────────────────────────────────────


@router.get("/devices")
async def list_devices(
    project_id: str = Depends(require_project),
    status: str | None = None,
    tag: str | None = None,
):
    devices = await mesh.list_devices(project_id, status=status, tag=tag)
    return {"devices": devices}


@router.post("/devices")
async def register_device(
    req: RegisterDeviceRequest,
    project_id: str = Depends(require_project),
):
    try:
        device = await mesh.register_device(
            project_id, req.name, req.host,
            ssh_port=req.ssh_port, ssh_user=req.ssh_user,
            tags=req.tags, metadata=req.metadata,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    # Generate install URL
    install_url = f"/api/projects/{project_id}/mesh/install/{device['install_token']}"

    return {
        "device": device,
        "install_token": device["install_token"],
        "install_url": install_url,
        "install_command": f"curl -fsSL https://nso.dev{install_url} | bash",
    }


@router.get("/devices/{device_id}")
async def get_device(
    device_id: str,
    project_id: str = Depends(require_project),
):
    try:
        device = await mesh.get_device(project_id, device_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"device": device}


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: str,
    req: UpdateDeviceRequest,
    project_id: str = Depends(require_project),
):
    try:
        device = await mesh.update_device(
            project_id, device_id,
            req.model_dump(exclude_none=True),
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"device": device}


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: str,
    project_id: str = Depends(require_project),
):
    try:
        await mesh.delete_device(project_id, device_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True, "device_id": device_id}


# ── Device activation (called by bootstrap script) ─────────────


@router.post("/devices/{device_id}/activate")
async def activate_device(
    device_id: str,
    req: ActivateDeviceRequest,
):
    """Public endpoint — validated by one-time install token."""
    try:
        device = await mesh.activate_device(
            device_id, req.token,
            fingerprint=req.fingerprint,
            os_info=req.os,
            agent_version=req.agent_version,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"device": device, "status": "activated"}


# ── Device operations ───────────────────────────────────────────


@router.post("/devices/{device_id}/exec")
async def exec_on_device(
    device_id: str,
    req: DeviceExecRequest,
    project_id: str = Depends(require_project),
):
    try:
        result = await mesh.exec_on_device(
            project_id, device_id, req.command,
            timeout=req.timeout, triggered_by="user",
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.get("/devices/{device_id}/status")
async def device_status(
    device_id: str,
    project_id: str = Depends(require_project),
):
    try:
        status = await mesh.get_device_status(project_id, device_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return status


@router.get("/devices/{device_id}/files")
async def list_device_files(
    device_id: str,
    project_id: str = Depends(require_project),
    path: str = "/",
):
    try:
        result = await mesh.list_device_files(project_id, device_id, path)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/devices/{device_id}/files/read")
async def read_device_file(
    device_id: str,
    project_id: str = Depends(require_project),
    path: str = "",
):
    if not path:
        raise HTTPException(400, "path is required")
    try:
        result = await mesh.read_device_file(project_id, device_id, path)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/devices/{device_id}/files/write")
async def write_device_file(
    device_id: str,
    project_id: str = Depends(require_project),
    path: str = "",
    content: str = "",
):
    if not path:
        raise HTTPException(400, "path is required")
    try:
        result = await mesh.write_device_file(project_id, device_id, path, content)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.get("/devices/{device_id}/logs")
async def device_logs(
    device_id: str,
    project_id: str = Depends(require_project),
    limit: int = 50,
):
    try:
        logs = await mesh.get_device_logs(project_id, device_id, limit)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"logs": logs}


# ── Groups ──────────────────────────────────────────────────────


@router.get("/groups")
async def list_groups(project_id: str = Depends(require_project)):
    groups = await mesh.list_groups(project_id)
    return {"groups": groups}


@router.post("/groups")
async def create_group(
    req: CreateGroupRequest,
    project_id: str = Depends(require_project),
):
    try:
        group = await mesh.create_group(project_id, req.name, req.description)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"group": group}


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: str,
    req: UpdateGroupRequest,
    project_id: str = Depends(require_project),
):
    try:
        group = await mesh.update_group(
            project_id, group_id,
            req.model_dump(exclude_none=True),
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"group": group}


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    project_id: str = Depends(require_project),
):
    try:
        await mesh.delete_group(project_id, group_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True, "group_id": group_id}


@router.post("/groups/{group_id}/devices")
async def add_devices_to_group(
    group_id: str,
    req: AddDevicesToGroupRequest,
    project_id: str = Depends(require_project),
):
    try:
        await mesh.add_devices_to_group(project_id, group_id, req.device_ids)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"added": len(req.device_ids)}


@router.delete("/groups/{group_id}/devices/{device_id}")
async def remove_device_from_group(
    group_id: str,
    device_id: str,
    project_id: str = Depends(require_project),
):
    try:
        await mesh.remove_device_from_group(project_id, group_id, device_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"removed": True}


# ── Group operations ────────────────────────────────────────────


@router.post("/groups/{group_id}/exec")
async def exec_on_group(
    group_id: str,
    req: GroupExecRequest,
    project_id: str = Depends(require_project),
):
    try:
        results = await mesh.exec_on_group(
            project_id, group_id, req.command,
            timeout=req.timeout,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"results": results}


@router.get("/groups/{group_id}/status")
async def group_status_endpoint(
    group_id: str,
    project_id: str = Depends(require_project),
):
    try:
        status = await mesh.group_status(project_id, group_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return status


# ── Bootstrap script (public, token-guarded) ────────────────────


@router.get("/install/{install_token}")
async def get_install_script(install_token: str):
    """Serve device-specific install script. Public endpoint, guarded by one-time token."""
    try:
        script = await generate_install_script(install_token)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return PlainTextResponse(
        script,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=nso-mesh-install.sh"},
    )
