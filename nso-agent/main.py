"""NSO Agent — Standalone VPS management service.

Runs on port 8081 on each provisioned VPS. Provides:
  - Admin authentication (JWT)
  - .zar deploy/snapshot/rollback
  - File system operations (browse, read, write, delete)
  - Command execution
  - Installation metrics tracking

Everything via HTTP. No SSH needed.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import store
from auth import (
    LoginRequest,
    LoginResponse,
    AdminUser,
    authenticate,
    require_admin,
)
from models import MetricReport, HealthResponse
from files import router as files_router
from exec import router as exec_router
from deploy import router as deploy_router
from envvars import router as secrets_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nso-agent")

HOST = os.environ.get("NSO_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("NSO_AGENT_PORT", "8081"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NSO Agent starting on %s:%d", HOST, PORT)
    await store.init()
    yield
    logger.info("NSO Agent shutting down")
    await store.close()


app = FastAPI(
    title="NSO Agent",
    description=(
        "VPS management agent for NSO. "
        "Provides admin auth, file operations, command execution, "
        "deploy/rollback, and metrics. Everything via HTTP."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Include routers ──────────────────────────────────────────────

app.include_router(files_router)
app.include_router(exec_router)
app.include_router(deploy_router)
app.include_router(secrets_router)


# ── Health (public) ──────────────────────────────────────────────

@app.get("/health")
async def health():
    count = await store.count_tracked()
    return HealthResponse(tracked_instances=count)


# ── Auth ─────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Login as admin. Returns JWT token.

    curl -X POST https://server:8081/auth/login \\
      -H "Content-Type: application/json" \\
      -d '{"email":"ayman_gha@hotmail.com","password":"xxx"}'
    """
    token = authenticate(req.email, req.password)
    if not token:
        raise HTTPException(401, "Invalid email or password")
    return LoginResponse(token=token, email=req.email)


@app.get("/auth/me")
async def whoami(admin: AdminUser = Depends(require_admin)):
    """Check current auth status."""
    return admin


# ── Metrics: Report (VPS → agent, public) ────────────────────────

@app.post("/report")
async def report_metric(data: MetricReport):
    """Receive a progress report during cloud-init.

    Called at each installation stage. No admin auth — uses provision_token.
    """
    existing = await store.get_metrics(data.instance_id)
    if existing:
        valid = await store.verify_token(data.instance_id, data.token)
        if not valid:
            raise HTTPException(403, "Invalid provision token")

    metrics = await store.report(data)
    logger.info(
        "[%s] stage=%s progress=%d%% — %s",
        data.instance_id, data.stage.value, metrics.progress, data.message,
    )
    return {"ok": True, "progress": metrics.progress, "stage": metrics.current_stage}


# ── Metrics: Register (API → agent) ──────────────────────────────

@app.post("/register")
async def register_instance(data: dict):
    """Register a new instance for metrics tracking.

    Called by NSO API when instance is created.
    """
    instance_id = data.get("instance_id")
    token = data.get("token")
    if not instance_id or not token:
        raise HTTPException(400, "instance_id and token required")

    await store.register_instance(instance_id, token)
    logger.info("Registered instance %s for tracking", instance_id)
    return {"ok": True, "instance_id": instance_id}


# ── Metrics: Status (public) ─────────────────────────────────────

@app.get("/status/{instance_id}")
async def get_status(instance_id: str):
    """Get installation metrics for an instance.

    curl https://server:8081/status/inst_abc123
    """
    metrics = await store.get_metrics(instance_id)
    if not metrics:
        raise HTTPException(404, f"No metrics for instance '{instance_id}'")
    return metrics


@app.delete("/status/{instance_id}")
async def delete_status(instance_id: str):
    """Remove metrics for an instance."""
    await store.delete_metrics(instance_id)
    return {"deleted": True}


# ── Entrypoint ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level="info",
    )
