"""
z86 Agent — Remote management for the z86 storage VPS.

Runs on port 8083, provides:
  - File browsing/editing (z86 code + storage data)
  - Command execution
  - Secret/env var management
  - Self-update deploy (z86 service + agent)
  - Auth via JWT

This agent lets you modify z86 in real time from the dashboard.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from auth import (
    LoginRequest,
    LoginResponse,
    AdminUser,
    authenticate,
    require_admin,
)
from files import router as files_router
from exec import router as exec_router
from deploy import router as deploy_router
from envvars import router as secrets_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("z86-agent")

HOST = os.environ.get("Z86_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("Z86_AGENT_PORT", "8083"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("z86 Agent starting on %s:%d", HOST, PORT)
    yield
    logger.info("z86 Agent shutting down")


app = FastAPI(
    title="z86 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files_router)
app.include_router(exec_router)
app.include_router(deploy_router)
app.include_router(secrets_router)


@app.get("/health")
async def health():
    import shutil
    # Report disk usage for storage monitoring
    data_dir = os.environ.get("Z86_DATA_DIR", "/data/z86")
    disk = {}
    try:
        usage = shutil.disk_usage(data_dir)
        disk = {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "used_pct": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        pass

    return {
        "service": "z86-agent",
        "status": "ok",
        "version": "0.1.0",
        "disk": disk,
    }


@app.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    token = authenticate(req.email, req.password)
    if not token:
        raise HTTPException(401, "Invalid email or password")
    return LoginResponse(token=token, email=req.email)


@app.get("/auth/me")
async def whoami(admin: AdminUser = Depends(require_admin)):
    return admin


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level="info",
    )
