import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("nso-agent.exec")
router = APIRouter(prefix="/exec", tags=["exec"])

MAX_TIMEOUT = 300
MAX_OUTPUT = 512 * 1024

ALLOWED_SERVICES = frozenset({"nso", "nso-agent", "nginx"})
VALID_SERVICE_ACTIONS = frozenset({"start", "stop", "restart", "status", "enable", "disable"})


class ExecRequest(BaseModel):
    command: str
    working_dir: str = "/opt/nso"
    timeout: int = Field(default=60, ge=1, le=MAX_TIMEOUT)
    env: dict[str, str] = Field(default_factory=dict)


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

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

@router.post("/", response_model=ExecResponse)
async def execute_command(
    req: ExecRequest,
    admin: AdminUser = Depends(require_admin),
):
    if _is_blocked(req.command):
        raise HTTPException(403, "Command blocked for safety")

    if not os.path.isdir(req.working_dir):
        req.working_dir = "/opt/nso"

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
    if action not in VALID_SERVICE_ACTIONS:
        raise HTTPException(400, f"Invalid action: {action}")

    if name not in ALLOWED_SERVICES:
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

    if action == "status":
        is_active = await asyncio.create_subprocess_shell(
            f"systemctl is-active {name}",
            stdout=asyncio.subprocess.PIPE,
        )
        out, _ = await is_active.communicate()
        result["active"] = out.decode().strip() == "active"

    return result
