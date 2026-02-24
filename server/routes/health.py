"""Health check + capabilities endpoint."""
import platform
from datetime import datetime

from fastapi import APIRouter

from core.models import Capabilities
from core.instances.types import INSTANCE_CONFIGS

router = APIRouter()

_start_time = datetime.utcnow()


@router.get("/health")
async def health():
    uptime = (datetime.utcnow() - _start_time).total_seconds()
    return {
        "status": "ok",
        "version": "0.2.0",
        "uptime_seconds": int(uptime),
        "platform": platform.system(),
    }


@router.get("/capabilities")
async def capabilities():
    """Agent-friendly endpoint: what can this API do?"""
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
            "instances.create", "instances.delete", "instances.stop", "instances.start",
            "instances.exec", "instances.deploy", "instances.logs",
            "domains.create", "domains.delete",
        ],
    ).model_dump()
