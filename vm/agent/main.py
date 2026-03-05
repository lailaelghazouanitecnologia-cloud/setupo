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
from supervisor import supervisor
from pool_handler import router as pool_router, _restore_vms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nso-agent")

HOST = os.environ.get("NSO_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("NSO_AGENT_PORT", "8081"))
_start_time = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    import time
    global _start_time
    _start_time = time.monotonic()
    logger.info("NSO Agent starting on %s:%d", HOST, PORT)
    await store.init()
    _restore_vms()  # restore VM state from disk
    await supervisor.start()
    yield
    logger.info("NSO Agent shutting down — draining processes")
    await supervisor.stop()
    await store.close()


app = FastAPI(
    title="NSO Agent",
    version="0.3.0",
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
app.include_router(pool_router)


@app.get("/health")
async def health():
    """Rich health endpoint — reports agent, system, and process state."""
    import time

    count = await store.count_tracked()

    # System metrics (read directly, no exec hack)
    system = {}
    try:
        st = os.statvfs("/")
        disk_total = st.f_blocks * st.f_frsize
        disk_free = st.f_bavail * st.f_frsize
        system["disk_percent"] = round((1 - disk_free / disk_total) * 100, 1) if disk_total else 0
        system["disk_free_gb"] = round(disk_free / (1024**3), 1)
    except Exception:
        pass

    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f.readlines()[:5]:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
            total = mem.get("MemTotal", 1)
            avail = mem.get("MemAvailable", mem.get("MemFree", 0))
            system["mem_percent"] = round((1 - avail / total) * 100, 1)
            system["mem_total_mb"] = round(total / 1024)
    except Exception:
        pass

    try:
        la = os.getloadavg()
        system["load"] = [round(la[0], 2), round(la[1], 2), round(la[2], 2)]
    except Exception:
        pass

    try:
        with open("/proc/uptime") as f:
            system["uptime"] = int(float(f.read().split()[0]))
    except Exception:
        pass

    sup_status = supervisor.get_status()

    return {
        "agent_version": "0.3.0",
        "agent_uptime": round(time.monotonic() - _start_time),
        "tracked_instances": count,
        "system": system,
        "supervisor": sup_status,
        "converged": sup_status["converged"],
    }


@app.get("/supervisor/status")
async def supervisor_status(admin: AdminUser = Depends(require_admin)):
    """Detailed supervisor state."""
    return supervisor.get_status()


@app.post("/supervisor/apply")
async def supervisor_apply(data: dict, admin: AdminUser = Depends(require_admin)):
    """
    Apply desired process specs to the supervisor.

    Body: {"processes": [{"name": "api", "command": "...", "port": 8000, ...}], "version": "1.0.0"}
    """
    from supervisor import ProcessSpec

    processes = data.get("processes", [])
    version = data.get("version", "")

    if not processes:
        raise HTTPException(400, "No processes specified")

    specs = []
    for p in processes:
        if not p.get("name") or not p.get("command"):
            raise HTTPException(400, f"Process spec missing name or command: {p}")
        specs.append(ProcessSpec.from_dict({**p, "version": version}))

    supervisor.set_desired(specs, version=version)

    return {
        "ok": True,
        "spec_generation": supervisor.spec_generation,
        "processes": [s.name for s in specs],
    }


@app.post("/supervisor/stop/{name}")
async def supervisor_stop_process(name: str, admin: AdminUser = Depends(require_admin)):
    """Remove a process from desired state (will be stopped by reconciler)."""
    if name not in supervisor.desired:
        raise HTTPException(404, f"Process '{name}' not in desired state")
    supervisor.remove_desired(name)
    return {"ok": True, "removed": name}

@app.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    token = authenticate(req.email, req.password)
    if not token:
        raise HTTPException(401, "Invalid email or password")
    return LoginResponse(token=token, email=req.email)


@app.get("/auth/me")
async def whoami(admin: AdminUser = Depends(require_admin)):
    return admin


@app.post("/report")
async def report_metric(data: MetricReport):
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

@app.post("/register")
async def register_instance(data: dict):
    instance_id = data.get("instance_id")
    token = data.get("token")
    if not instance_id or not token:
        raise HTTPException(400, "instance_id and token required")

    await store.register_instance(instance_id, token)
    logger.info("Registered instance %s for tracking", instance_id)
    return {"ok": True, "instance_id": instance_id}

@app.get("/status/{instance_id}")
async def get_status(instance_id: str):
    metrics = await store.get_metrics(instance_id)
    if not metrics:
        raise HTTPException(404, f"No metrics for instance '{instance_id}'")
    return metrics


@app.delete("/status/{instance_id}")
async def delete_status(instance_id: str):
    await store.delete_metrics(instance_id)
    return {"deleted": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True,
        log_level="info",
    )
