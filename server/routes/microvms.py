"""MicroVM (Firecracker) management routes."""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CreateMicroVMRequest(BaseModel):
    name: str
    vcpus: int = 1
    memory_mb: int = 256
    disk_mb: int = 512


@router.get("/")
async def list_microvms(request: Request):
    orch = request.app.state.orchestrator
    return {"microvms": orch.list_instances(vm_type="microvm")}


@router.post("/")
async def create_microvm(req: CreateMicroVMRequest, request: Request):
    orch = request.app.state.orchestrator
    instance = await orch.create_microvm(
        name=req.name,
        vcpus=req.vcpus,
        memory_mb=req.memory_mb,
        disk_mb=req.disk_mb,
    )
    return {"microvm": instance.to_dict()}


@router.get("/{vm_id}")
async def get_microvm(vm_id: str, request: Request):
    orch = request.app.state.orchestrator
    try:
        return {"microvm": orch.get_instance(vm_id)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{vm_id}/stop")
async def stop_microvm(vm_id: str, request: Request):
    orch = request.app.state.orchestrator
    try:
        instance = await orch.stop_instance(vm_id)
        return {"microvm": instance.to_dict()}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{vm_id}/start")
async def start_microvm(vm_id: str, request: Request):
    """Restart a stopped MicroVM."""
    orch = request.app.state.orchestrator
    try:
        inst = orch.instances.get(vm_id)
        if not inst:
            raise HTTPException(404, f"MicroVM {vm_id} not found")
        if inst.state.value == "running":
            raise HTTPException(400, "MicroVM already running")
        await orch._boot_microvm(inst)
        inst.state = "running"
        return {"microvm": inst.to_dict()}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{vm_id}")
async def destroy_microvm(vm_id: str, request: Request):
    orch = request.app.state.orchestrator
    try:
        return await orch.destroy_instance(vm_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
