"""MMS Agent — Command execution on the VPS.

Run commands, get output. Like SSH but via HTTP.
"""
import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("mms-agent.exec")
router = APIRouter(prefix="/exec", tags=["exec"])

MAX_TIMEOUT = 300  # 5 minutes max
MAX_OUTPUT = 1024 * 512  # 512KB max output


# ── Models ───────────────────────────────────────────────────────

class ExecRequest(BaseModel):
    command: str
    working_dir: str = "/opt/mms"
    timeout: int = Field(default=60, ge=1, le=MAX_TIMEOUT)
    env: dict[str, str] = Field(default_factory=dict)


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


# ── Blocked commands (safety) ────────────────────────────────────

BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init 0",
    "init 6",
]


def _is_blocked(command: str) -> bool:
    cmd_lower = command.lower().strip()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return True
    return False


# ── Endpoint ─────────────────────────────────────────────────────

@router.post("/", response_model=ExecResponse)
async def execute_command(
    req: ExecRequest,
    admin: AdminUser = Depends(require_admin),
):
    """Execute a shell command on the VPS.

    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"command":"ls -la /opt/mms","timeout":30}' \\
      https://server:8081/exec/

    Examples:
      {"command": "systemctl status mms"}
      {"command": "pip install requests", "working_dir": "/opt/app"}
      {"command": "cat /var/log/mms/error.log", "timeout": 10}
      {"command": "python3 -c 'print(1+1)'"}
    """
    if _is_blocked(req.command):
        raise HTTPException(403, "Command blocked for safety")

    # Validate working dir exists
    if not os.path.isdir(req.working_dir):
        req.working_dir = "/opt/mms"

    env = {**os.environ, **req.env}

    logger.info("exec: %s (cwd=%s, timeout=%d)", req.command, req.working_dir, req.timeout)

    try:
        proc = await asyncio.create_subprocess_shell(
            req.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=req.working_dir,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=req.timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Command timed out: %s", req.command)
            return ExecResponse(
                stdout="",
                stderr=f"Command timed out after {req.timeout}s",
                exit_code=-1,
                timed_out=True,
            )

        stdout = stdout_bytes.decode(errors="replace")[:MAX_OUTPUT]
        stderr = stderr_bytes.decode(errors="replace")[:MAX_OUTPUT]

        logger.info("exec complete: exit_code=%d, stdout=%d bytes", proc.returncode, len(stdout))

        return ExecResponse(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode or 0,
        )

    except Exception as e:
        logger.error("exec error: %s", e)
        raise HTTPException(500, f"Execution failed: {e}")


@router.post("/service")
async def manage_service(
    action: str,
    name: str,
    admin: AdminUser = Depends(require_admin),
):
    """Manage a systemd service (start/stop/restart/status).

    curl -X POST -H "Authorization: Bearer <token>" \\
      "https://server:8081/exec/service?action=restart&name=mms"
    """
    if action not in ("start", "stop", "restart", "status", "enable", "disable"):
        raise HTTPException(400, f"Invalid action: {action}")

    # Only allow known service names
    allowed = {"mms", "mms-metrics", "mms-app", "nginx"}
    if name not in allowed:
        raise HTTPException(403, f"Service not in allowed list: {name}")

    cmd = f"systemctl {action} {name}"
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    result = {
        "service": name,
        "action": action,
        "exit_code": proc.returncode,
        "output": stdout.decode(errors="replace"),
    }

    # For status, also get is-active
    if action == "status":
        is_active = await asyncio.create_subprocess_shell(
            f"systemctl is-active {name}",
            stdout=asyncio.subprocess.PIPE,
        )
        out, _ = await is_active.communicate()
        result["active"] = out.decode().strip() == "active"

    return result
