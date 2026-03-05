"""
Compute Pool API — manage hosts, VMs, and plans.

Admin-only endpoints for pool infrastructure management.
Public endpoint for listing available plans.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from nso.shared.deps import require_admin, require_project
from nso.engine.compute import pool

router = APIRouter()


# ── Request models ──

class RegisterHostRequest(BaseModel):
    provider: str = "vultr"
    provider_id: str
    ip: str
    region: str = "ewr"
    plan: str = ""
    vcpus: int
    ram_mb: int
    disk_gb: int
    bandwidth_gb: int = 0
    cost_cents: int = 0
    label: str = ""
    cpu_overcommit: float = 1.5
    ram_overcommit: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateHostRequest(BaseModel):
    status: Optional[str] = None
    cpu_overcommit: Optional[float] = None
    ram_overcommit: Optional[float] = None
    label: Optional[str] = None


class HostMetricsReport(BaseModel):
    cpu_percent: float
    ram_percent: float
    disk_percent: float


class AllocateVMRequest(BaseModel):
    plan: str
    region: str = ""
    label: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePlanRequest(BaseModel):
    code: str
    name: str
    vcpus: int
    ram_mb: int
    disk_gb: int
    bandwidth_gb: int = 100
    price_cents_monthly: int = 0
    price_cents_hourly: int = 0
    max_processes: int = 5
    max_domains: int = 1
    max_deployments_day: int = 10
    description: str = ""


# ── Plans (public) ──

@router.get("/plans")
async def list_plans():
    """List available compute plans."""
    plans = await pool.list_plans(available_only=True)
    return {"plans": plans}


@router.get("/plans/{code}")
async def get_plan(code: str):
    """Get plan details."""
    plan = await pool.get_plan(code)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return {"plan": plan}


# ── Plans (admin) ──

@router.post("/plans", dependencies=[Depends(require_admin)])
async def create_plan(req: CreatePlanRequest):
    """Create a custom compute plan (admin)."""
    existing = await pool.get_plan(req.code)
    if existing:
        raise HTTPException(409, f"Plan '{req.code}' already exists")
    plan = await pool.create_plan(
        code=req.code, name=req.name, vcpus=req.vcpus,
        ram_mb=req.ram_mb, disk_gb=req.disk_gb, bandwidth_gb=req.bandwidth_gb,
        price_cents_monthly=req.price_cents_monthly,
        price_cents_hourly=req.price_cents_hourly,
        max_processes=req.max_processes, max_domains=req.max_domains,
        max_deployments_day=req.max_deployments_day, description=req.description,
    )
    return {"plan": plan}


# ── Pool overview (admin) ──

@router.get("/overview", dependencies=[Depends(require_admin)])
async def get_pool_overview():
    """Get aggregate pool stats — capacity, utilization, economics."""
    overview = await pool.pool_overview()
    return overview


# ── Host management (admin) ──

@router.get("/hosts", dependencies=[Depends(require_admin)])
async def list_hosts(status: str = ""):
    """List all hosts in the pool."""
    hosts = await pool.list_hosts(status=status)
    return {"hosts": hosts, "total": len(hosts)}


@router.post("/hosts", dependencies=[Depends(require_admin)])
async def register_host(req: RegisterHostRequest):
    """Register a new host machine in the pool."""
    host = await pool.register_host(
        provider=req.provider, provider_id=req.provider_id, ip=req.ip,
        region=req.region, plan=req.plan, vcpus=req.vcpus,
        ram_mb=req.ram_mb, disk_gb=req.disk_gb, bandwidth_gb=req.bandwidth_gb,
        cost_cents=req.cost_cents, label=req.label,
        cpu_overcommit=req.cpu_overcommit, ram_overcommit=req.ram_overcommit,
        metadata=req.metadata,
    )
    return {"host": host}


@router.get("/hosts/{host_id}", dependencies=[Depends(require_admin)])
async def get_host(host_id: str):
    """Get host details with its VMs."""
    host = await pool.get_host(host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    return {"host": host}


@router.patch("/hosts/{host_id}", dependencies=[Depends(require_admin)])
async def update_host(host_id: str, req: UpdateHostRequest):
    """Update host status or config."""
    host = await pool.get_host(host_id)
    if not host:
        raise HTTPException(404, "Host not found")

    if req.status:
        await pool.set_host_status(host_id, req.status)

    from nso.shared import db
    updates = {}
    if req.cpu_overcommit is not None:
        updates["cpu_overcommit"] = req.cpu_overcommit
    if req.ram_overcommit is not None:
        updates["ram_overcommit"] = req.ram_overcommit
    if req.label is not None:
        updates["label"] = req.label
    if updates:
        await db.update("compute_hosts", host_id, updates)

    return {"updated": True, "host_id": host_id}


@router.post("/hosts/{host_id}/metrics", dependencies=[Depends(require_admin)])
async def report_host_metrics(host_id: str, req: HostMetricsReport):
    """Report host metrics (called by host agent)."""
    host = await pool.get_host(host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    await pool.update_host_metrics(host_id, req.cpu_percent, req.ram_percent, req.disk_percent)
    return {"ok": True}


# ── VM management ──

@router.get("/vms", dependencies=[Depends(require_admin)])
async def list_all_vms(host_id: str = ""):
    """List all VMs, optionally filtered by host."""
    vms = await pool.list_vms(host_id=host_id)
    return {"vms": vms, "total": len(vms)}


@router.post("/vms")
async def allocate_vm(req: AllocateVMRequest, project_id: str = Depends(require_project)):
    """Allocate a VM on the pool for a project."""
    try:
        vm = await pool.allocate_vm(
            project_id=project_id,
            plan_code=req.plan,
            region=req.region,
            label=req.label,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"vm": vm}


@router.get("/vms/project")
async def list_project_vms(project_id: str = Depends(require_project)):
    """List VMs for the current project."""
    vms = await pool.list_vms(project_id=project_id)
    return {"vms": vms, "total": len(vms)}


@router.get("/vms/{vm_id}")
async def get_vm(vm_id: str, project_id: str = Depends(require_project)):
    """Get VM details."""
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise HTTPException(404, "VM not found")
    if vm["project_id"] != project_id:
        raise HTTPException(403, "VM belongs to another project")
    return {"vm": vm}


@router.delete("/vms/{vm_id}")
async def release_vm(vm_id: str, project_id: str = Depends(require_project)):
    """Release a VM and free its resources."""
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise HTTPException(404, "VM not found")
    if vm["project_id"] != project_id:
        raise HTTPException(403, "VM belongs to another project")
    released = await pool.release_vm(vm_id)
    return {"released": released, "vm_id": vm_id}


@router.post("/vms/{vm_id}/status", dependencies=[Depends(require_admin)])
async def update_vm_status(vm_id: str, status: str):
    """Update VM status (admin)."""
    vm = await pool.get_vm(vm_id)
    if not vm:
        raise HTTPException(404, "VM not found")
    await pool.set_vm_status(vm_id, status)
    return {"updated": True, "vm_id": vm_id, "status": status}
