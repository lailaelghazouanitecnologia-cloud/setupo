"""MMS Services - Manage running processes with port assignment."""
import asyncio
import os
import signal
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.auth import require_token

logger = logging.getLogger("mms.services")
router = APIRouter()

# In-memory service registry
_services: dict[str, dict] = {}
_next_port = 8001


class CreateServiceRequest(BaseModel):
    name: str
    command: str
    working_dir: str = "/opt/mms"
    env: dict[str, str] = {}
    port: int | None = None  # Auto-assign if None


class ServiceResponse(BaseModel):
    id: str
    name: str
    command: str
    port: int | None
    pid: int | None
    status: str
    working_dir: str
    started_at: str | None
    output_lines: int


def _get_service(name: str) -> dict:
    if name not in _services:
        raise HTTPException(404, f"Service '{name}' not found")
    return _services[name]


@router.get("/")
async def list_services(_=Depends(require_token)):
    """List all services."""
    result = []
    for name, svc in _services.items():
        proc: asyncio.subprocess.Process | None = svc.get("process")
        status = "stopped"
        if proc and proc.returncode is None:
            status = "running"
        elif proc and proc.returncode is not None:
            status = f"exited({proc.returncode})"

        result.append({
            "id": name,
            "name": name,
            "command": svc["command"],
            "port": svc.get("port"),
            "pid": proc.pid if proc and proc.returncode is None else None,
            "status": status,
            "working_dir": svc["working_dir"],
            "started_at": svc.get("started_at"),
            "output_lines": len(svc.get("output", [])),
        })
    return {"services": result, "count": len(result)}


@router.post("/")
async def create_service(req: CreateServiceRequest, _=Depends(require_token)):
    """Create and start a service."""
    global _next_port

    if req.name in _services:
        raise HTTPException(409, f"Service '{req.name}' already exists")

    port = req.port or _next_port
    if not req.port:
        _next_port += 1

    env = {**os.environ, **req.env, "PORT": str(port)}
    work_dir = req.working_dir

    if not os.path.isdir(work_dir):
        raise HTTPException(400, f"Working directory not found: {work_dir}")

    # Start process
    try:
        proc = await asyncio.create_subprocess_shell(
            req.command,
            cwd=work_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=os.setsid,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to start: {e}")

    svc = {
        "name": req.name,
        "command": req.command,
        "port": port,
        "working_dir": work_dir,
        "process": proc,
        "started_at": datetime.utcnow().isoformat(),
        "output": [],
    }
    _services[req.name] = svc

    # Background task to capture output
    async def _capture():
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode(errors="replace").rstrip()
                svc["output"].append(decoded)
                if len(svc["output"]) > 1000:
                    svc["output"] = svc["output"][-500:]
        except Exception:
            pass

    asyncio.create_task(_capture())
    logger.info("Service '%s' started (pid=%d, port=%d)", req.name, proc.pid, port)

    return {
        "service": {
            "id": req.name,
            "name": req.name,
            "command": req.command,
            "port": port,
            "pid": proc.pid,
            "status": "running",
            "working_dir": work_dir,
            "started_at": svc["started_at"],
        }
    }


@router.post("/{name}/stop")
async def stop_service(name: str, _=Depends(require_token)):
    """Stop a running service."""
    svc = _get_service(name)
    proc = svc.get("process")
    if not proc or proc.returncode is not None:
        raise HTTPException(400, "Service is not running")

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass

    logger.info("Service '%s' stopped", name)
    return {"name": name, "status": "stopped"}


@router.post("/{name}/restart")
async def restart_service(name: str, _=Depends(require_token)):
    """Restart a service."""
    svc = _get_service(name)
    proc = svc.get("process")

    # Stop if running
    if proc and proc.returncode is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass

    # Restart
    env = {**os.environ, "PORT": str(svc.get("port", 8001))}
    new_proc = await asyncio.create_subprocess_shell(
        svc["command"],
        cwd=svc["working_dir"],
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    svc["process"] = new_proc
    svc["output"] = []
    svc["started_at"] = datetime.utcnow().isoformat()

    async def _capture():
        try:
            while True:
                line = await new_proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode(errors="replace").rstrip()
                svc["output"].append(decoded)
                if len(svc["output"]) > 1000:
                    svc["output"] = svc["output"][-500:]
        except Exception:
            pass

    asyncio.create_task(_capture())
    logger.info("Service '%s' restarted (pid=%d)", name, new_proc.pid)
    return {"name": name, "status": "running", "pid": new_proc.pid}


@router.get("/{name}/logs")
async def service_logs(name: str, tail: int = 100, _=Depends(require_token)):
    """Get service output logs."""
    svc = _get_service(name)
    lines = svc.get("output", [])
    return {"name": name, "logs": lines[-tail:], "total": len(lines)}


@router.delete("/{name}")
async def delete_service(name: str, _=Depends(require_token)):
    """Stop and remove a service."""
    svc = _get_service(name)
    proc = svc.get("process")
    if proc and proc.returncode is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=3)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass

    del _services[name]
    logger.info("Service '%s' deleted", name)
    return {"deleted": name}
