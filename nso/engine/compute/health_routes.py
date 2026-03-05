import platform
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from nso.shared.models import Capabilities
from nso.shared.deps import require_admin
from nso.engine.compute.types import INSTANCE_CONFIGS

router = APIRouter()

_start_time = datetime.now(timezone.utc)


@router.get("/health")
async def health():
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return {
        "status": "ok",
        "version": "0.2.0",
        "uptime_seconds": int(uptime),
        "platform": platform.system(),
    }


@router.get("/services", dependencies=[Depends(require_admin)])
async def services_status(request: Request):
    """Get status of all background services (admin only)."""
    services = getattr(request.app.state, "services", None)
    if not services:
        return {"services": {}, "message": "ServiceManager not active (user mode)"}
    return services.status()


@router.get("/capabilities")
async def capabilities():
    return Capabilities(
        version="0.2.0",
        instance_types=[
            {
                "type": t,
                "description": cfg["description"],
                "default_plan": cfg["default_plan"],
                "features": cfg["features"],
            }
            for t, cfg in INSTANCE_CONFIGS.items()
        ],
        regions=[
            {"id": "ewr", "city": "New Jersey", "country": "US"},
            {"id": "ord", "city": "Chicago", "country": "US"},
            {"id": "dfw", "city": "Dallas", "country": "US"},
            {"id": "lax", "city": "Los Angeles", "country": "US"},
            {"id": "atl", "city": "Atlanta", "country": "US"},
            {"id": "mia", "city": "Miami", "country": "US"},
            {"id": "ams", "city": "Amsterdam", "country": "NL"},
            {"id": "lhr", "city": "London", "country": "GB"},
            {"id": "fra", "city": "Frankfurt", "country": "DE"},
            {"id": "cdg", "city": "Paris", "country": "FR"},
            {"id": "nrt", "city": "Tokyo", "country": "JP"},
            {"id": "sgp", "city": "Singapore", "country": "SG"},
        ],
        plans=[
            {"id": "vc2-1c-1gb", "vcpu": 1, "ram_mb": 1024, "disk_gb": 25, "bandwidth_tb": 1, "price_monthly": 5},
            {"id": "vc2-1c-2gb", "vcpu": 1, "ram_mb": 2048, "disk_gb": 55, "bandwidth_tb": 2, "price_monthly": 10},
            {"id": "vc2-2c-4gb", "vcpu": 2, "ram_mb": 4096, "disk_gb": 80, "bandwidth_tb": 3, "price_monthly": 20},
            {"id": "vc2-4c-8gb", "vcpu": 4, "ram_mb": 8192, "disk_gb": 160, "bandwidth_tb": 4, "price_monthly": 40},
            {"id": "vc2-6c-16gb", "vcpu": 6, "ram_mb": 16384, "disk_gb": 320, "bandwidth_tb": 5, "price_monthly": 80},
        ],
        actions=[
            "projects.create", "projects.delete", "projects.rotate_key",
            "workspaces.create", "workspaces.delete", "workspaces.pull", "workspaces.files",
            "workspaces.pack", "workspaces.push", "workspaces.deploy",
            "workspaces.ship", "workspaces.rollback",
            "workspaces.branch", "workspaces.merge", "workspaces.versions",
            "instances.create", "instances.delete", "instances.stop", "instances.start",
            "instances.exec", "instances.deploy", "instances.logs",
            "instances.self_update",
            "domains.create", "domains.delete",
        ],
    ).model_dump()
