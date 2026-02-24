"""Health check - public endpoint."""
import platform
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    engine = request.app.state.engine
    stats = await engine.get_stats()
    return {
        "status": "ok",
        "service": "mms",
        "version": "0.1.0",
        "platform": platform.platform(),
        **stats,
    }
