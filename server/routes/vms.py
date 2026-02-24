"""Full VM (QEMU/KVM) management routes."""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CreateVMRequest(BaseModel):
    name: str
    vcpus: int = 2
    memory_mb: int = 1024
    disk_mb: int = 4096
    image: str = "debian"


@router.get("/")
async def list_vms(request: Request):
    orch = request.app.state.orchestrator
    return {"vms": orch.list_instances(vm_type="vm")}


@router.post("/")
async def create_vm(req: CreateVMRequest, request: Request):
    orch = request.app.state.orchestrator
    instance = await orch.create_vm(
        name=req.name,
        vcpus=req.vcpus,
        memory_mb=req.memory_mb,
        disk_mb=req.disk_mb,
        image=req.image,
    )
    return {"vm": instance.to_dict()}


@router.get("/{vm_id}")
async def get_vm(vm_id: str, request: Request):
    orch = request.app.state.orchestrator
    try:
        return {"vm": orch.get_instance(vm_id)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{vm_id}/stop")
async def stop_vm(vm_id: str, request: Request):
    orch = request.app.state.orchestrator
    try:
        instance = await orch.stop_instance(vm_id)
        return {"vm": instance.to_dict()}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{vm_id}")
async def destroy_vm(vm_id: str, request: Request):
    orch = request.app.state.orchestrator
    try:
        return await orch.destroy_instance(vm_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
