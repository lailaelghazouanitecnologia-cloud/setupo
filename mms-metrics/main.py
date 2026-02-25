"""MMS Metrics — Standalone installation metrics service.

Lightweight FastAPI service running on port 8081.
Receives progress reports from VPS instances during cloud-init
and serves installation status to users/agents via curl.

Usage:
    curl POST /report         — VPS reports its stage
    curl GET  /status/{id}    — Check installation progress
    curl GET  /health         — Service health check

Example:
    # Check installation progress
    curl https://your-server:8081/status/inst_abc123

    # VPS reports (called from cloud-init)
    curl -X POST https://your-server:8081/report \
      -H "Content-Type: application/json" \
      -d '{"instance_id":"inst_abc","token":"prov_xxx","stage":"packages","message":"Installing nginx..."}'
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import store
from models import MetricReport, HealthResponse, InstanceMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mms-metrics")

HOST = os.environ.get("MMS_METRICS_HOST", "0.0.0.0")
PORT = int(os.environ.get("MMS_METRICS_PORT", "8081"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("mms-metrics starting on %s:%d", HOST, PORT)
    await store.init()
    yield
    logger.info("mms-metrics shutting down")
    await store.close()


app = FastAPI(
    title="MMS Metrics",
    description="Installation progress tracking for MMS instances",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    count = await store.count_tracked()
    return HealthResponse(tracked_instances=count)


# ── Report (VPS → mms-metrics) ──────────────────────────────────

@app.post("/report")
async def report_metric(data: MetricReport):
    """Receive a progress report from a VPS during cloud-init.

    Called by the cloud-init script at each installation stage.
    Requires a valid provision_token for authentication.
    """
    # Verify token (unless it's the first report which auto-registers)
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


# ── Register (MMS API → mms-metrics) ────────────────────────────

@app.post("/register")
async def register_instance(data: dict):
    """Register a new instance for tracking.

    Called by the MMS API when an instance is created.
    Body: { "instance_id": "inst_xxx", "token": "prov_xxx" }
    """
    instance_id = data.get("instance_id")
    token = data.get("token")
    if not instance_id or not token:
        raise HTTPException(400, "instance_id and token required")

    await store.register_instance(instance_id, token)
    logger.info("Registered instance %s for tracking", instance_id)
    return {"ok": True, "instance_id": instance_id}


# ── Status (user/agent queries) ─────────────────────────────────

@app.get("/status/{instance_id}")
async def get_status(instance_id: str):
    """Get installation metrics for an instance.

    This is the main endpoint for checking progress:
        curl https://your-server:8081/status/inst_abc123
    """
    metrics = await store.get_metrics(instance_id)
    if not metrics:
        raise HTTPException(404, f"No metrics for instance '{instance_id}'")
    return metrics


# ── Cleanup ──────────────────────────────────────────────────────

@app.delete("/status/{instance_id}")
async def delete_status(instance_id: str):
    """Remove metrics for an instance (cleanup after done)."""
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
