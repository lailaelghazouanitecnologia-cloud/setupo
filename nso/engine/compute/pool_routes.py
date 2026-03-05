"""
Compute Pool API — manage hosts, VMs, and plans.

Admin-only endpoints for pool infrastructure management.
Public endpoint for listing available plans.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from nso.shared.deps import require_admin, require_project, get_auth
from nso.shared.auth.resolve import AuthContext
from nso.engine.compute import pool
from nso.engine.compute.types import get_cloud_init
from nso.engine.compute import quota as compute_quota

router = APIRouter()


# ── Request models ──

class RegisterHostRequest(BaseModel):
    provider: str = "vultr"
    provider_id: str = ""
    ip: str = ""
    region: str = "ewr"
    plan: str = ""
    vcpus: int = 0
    ram_mb: int = 0
    disk_gb: int = 0
    bandwidth_gb: int = 0
    cost_cents: int = 0
    label: str = ""
    cpu_overcommit: float = 1.5
    ram_overcommit: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProvisionPoolHostRequest(BaseModel):
    """Provision a new pool host via Vultr — creates VPS with hardened cloud-init."""
    region: str = "ewr"
    plan: str = "vhp-4c-8gb-intel"
    label: str = ""
    cpu_overcommit: float = 1.5
    ram_overcommit: float = 1.0


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
    """Register an existing host machine in the pool (manual setup)."""
    host = await pool.register_host(
        provider=req.provider, provider_id=req.provider_id, ip=req.ip,
        region=req.region, plan=req.plan, vcpus=req.vcpus,
        ram_mb=req.ram_mb, disk_gb=req.disk_gb, bandwidth_gb=req.bandwidth_gb,
        cost_cents=req.cost_cents, label=req.label,
        cpu_overcommit=req.cpu_overcommit, ram_overcommit=req.ram_overcommit,
        metadata=req.metadata,
    )
    return {"host": host}


@router.post("/hosts/provision", dependencies=[Depends(require_admin)])
async def provision_pool_host(req: ProvisionPoolHostRequest):
    """
    Provision a new pool host via Vultr with hardened cloud-init.

    This:
    1. Creates a Vultr VPS with the pool-host cloud-init
    2. Registers it in the pool DB
    3. The cloud-init installs Docker, hardens the kernel, sets up firewall,
       and configures the agent with the pool token

    The host will be ready to accept VMs once cloud-init completes (~3-5 min).
    """
    import asyncio
    import secrets as _secrets
    from nso.config import settings
    from nso.engine.compute.providers.vultr import VultrProvider

    # Pre-generate the agent token so we can bake it into cloud-init
    agent_token = _secrets.token_hex(32)

    # Get central server IP for firewall whitelist
    central_ip = getattr(settings, "NSO_PUBLIC_IP", "") or "0.0.0.0"

    user_data = get_cloud_init(
        "pool_host",
        pool_agent_token=agent_token,
        central_server_ip=central_ip,
    )

    vultr = VultrProvider()
    try:
        vps = await vultr.create_instance(
            region=req.region,
            plan=req.plan,
            os_id=settings.VULTR_DEFAULT_OS,
            label=req.label or "nso-pool-host",
            user_data=user_data,
            tag="nso-pool",
        )

        provider_id = vps.get("id", "")

        # Poll for IP
        ip = ""
        for _ in range(60):
            await asyncio.sleep(5)
            data = await vultr.get_instance(provider_id)
            if not data:
                continue
            status = data.get("status", "")
            power = data.get("power_status", "")
            main_ip = data.get("main_ip", "")
            if status == "active" and power == "running" and main_ip and main_ip != "0.0.0.0":
                ip = main_ip
                break

        if not ip:
            raise HTTPException(504, "Pool host did not get an IP within timeout")

        # Get plan specs from Vultr response
        vcpus = vps.get("vcpu_count", 4)
        ram_mb = vps.get("ram", 8192)
        disk_gb = vps.get("disk", 160)

        # Register in pool DB
        host = await pool.register_host(
            provider="vultr",
            provider_id=provider_id,
            ip=ip,
            region=req.region,
            plan=req.plan,
            vcpus=vcpus,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            cost_cents=0,
            label=req.label or f"pool-{ip}",
            cpu_overcommit=req.cpu_overcommit,
            ram_overcommit=req.ram_overcommit,
        )

        # Override the auto-generated token with the one baked into cloud-init
        from nso.shared import db
        await db.update("compute_hosts", host["id"], {"agent_token": agent_token})
        host["agent_token"] = agent_token

        return {
            "host": host,
            "vultr_id": provider_id,
            "ip": ip,
            "status": "provisioning",
            "message": "Cloud-init is running. Host will be ready for VMs in ~3-5 minutes.",
        }
    finally:
        await vultr.close()


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
async def allocate_vm(
    req: AllocateVMRequest,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(get_auth),
):
    """Allocate a VM on the pool for a project. Enforces project quota."""
    # Admins bypass quota checks
    quota_info = None
    if not auth.is_admin:
        try:
            quota_info = await compute_quota.check_quota(project_id, req.plan)
        except Exception as e:
            raise HTTPException(403, str(e))

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

    result = {"vm": vm}
    if quota_info:
        result["quota"] = quota_info
    return result


@router.get("/usage")
async def get_usage(project_id: str = Depends(require_project)):
    """Get current resource usage vs. project quota limits."""
    usage = await compute_quota.get_project_usage(project_id)
    return usage


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


# ── Quota management (admin) ──

class SetQuotaRequest(BaseModel):
    max_vms: Optional[int] = None
    max_vcpus: Optional[int] = None
    max_ram_mb: Optional[int] = None
    allowed_plans: Optional[list[str]] = None
    notes: str = ""


@router.get("/quota/{project_id}", dependencies=[Depends(require_admin)])
async def get_project_quota(project_id: str):
    """Get quota for a project (admin)."""
    quota = await compute_quota.get_project_quota(project_id)
    usage = await compute_quota.get_project_usage(project_id)
    return {"quota": quota, "usage": usage}


@router.put("/quota/{project_id}", dependencies=[Depends(require_admin)])
async def set_project_quota(project_id: str, req: SetQuotaRequest):
    """Set or update quota for a project (admin)."""
    quota = await compute_quota.set_project_quota(
        project_id=project_id,
        max_vms=req.max_vms,
        max_vcpus=req.max_vcpus,
        max_ram_mb=req.max_ram_mb,
        allowed_plans=req.allowed_plans,
        notes=req.notes,
    )
    return {"quota": quota}


@router.delete("/quota/{project_id}", dependencies=[Depends(require_admin)])
async def delete_project_quota(project_id: str):
    """Remove custom quota, reverting to defaults (admin)."""
    deleted = await compute_quota.delete_project_quota(project_id)
    return {"deleted": deleted, "project_id": project_id}
