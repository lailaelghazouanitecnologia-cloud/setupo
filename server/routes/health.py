"""Health check endpoint - public, no auth required."""
import platform
import shutil
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    orch = request.app.state.orchestrator
    disk = shutil.disk_usage("/")
    return {
        "status": "ok",
        "version": "0.1.0",
        "platform": platform.platform(),
        "instances": {
            "total": len(orch.instances),
            "running": sum(1 for i in orch.instances.values() if i.state.value == "running"),
            "stopped": sum(1 for i in orch.instances.values() if i.state.value == "stopped"),
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
        },
    }
