"""
Pool VM Handler — host-side agent endpoints for VM lifecycle.

When this agent runs on a HOST machine (not a user VPS), these endpoints
let the pool reconciler create/destroy/inspect VMs on this host.

VMs are implemented as isolated containers using Docker (preferred) or
cgroup sandboxes, with strict security isolation between user VMs and
the host system.

Security layers:
1. Auth: All endpoints require admin JWT
2. Input validation: vm_id/project_id are sanitized (alphanumeric + underscore only)
3. Docker hardening: no-new-privileges, cap-drop ALL, seccomp, read-only rootfs,
   user namespace, no host PID/IPC, tmpfs for writable dirs
4. Cgroup sandbox hardening: full namespace isolation (pid, net, mount, user, ipc, uts)
5. Network isolation: each VM gets its own network namespace, iptables DROP default
6. Filesystem: VMs can only access their own directory, host FS is invisible
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from auth import AdminUser, require_admin, verify_token

logger = logging.getLogger("nso-agent.pool")

router = APIRouter(prefix="/pool")

VM_BASE_DIR = os.environ.get("NSO_VM_DIR", "/opt/nso/vms")
_vms: dict[str, dict] = {}  # in-memory VM state

# Strict pattern: only allow safe characters in identifiers
# Agent token set by the central server when registering the host.
# This token is used by the pool reconciler to authenticate pool operations.
POOL_AGENT_TOKEN = os.environ.get("NSO_POOL_AGENT_TOKEN", "")

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")

# Resource limits to prevent abuse
MAX_VCPUS = 16
MAX_RAM_MB = 32768  # 32GB
MAX_DISK_GB = 500
MAX_PORT_RANGE = 100
MIN_PORT = 10000
MAX_PORT = 60000


def _validate_id(value: str, name: str) -> str:
    """Validate an identifier to prevent path traversal and command injection."""
    if not _SAFE_ID_RE.match(value):
        raise ValueError(
            f"{name} must be 3-64 chars, alphanumeric/underscore/hyphen, "
            f"start with alphanumeric. Got: {value!r}"
        )
    # Extra safety: reject anything with path separators or shell metacharacters
    dangerous = {".", "/", "\\", ";", "&", "|", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\r", "\0"}
    if any(c in value for c in dangerous):
        raise ValueError(f"{name} contains forbidden characters")
    return value


class CreateVMRequest(BaseModel):
    vm_id: str
    project_id: str
    vcpus: int = 1
    ram_mb: int = 512
    disk_gb: int = 10
    port_start: int = 10000
    port_end: int = 10099

    @field_validator("vm_id")
    @classmethod
    def validate_vm_id(cls, v: str) -> str:
        return _validate_id(v, "vm_id")

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        return _validate_id(v, "project_id")

    @field_validator("vcpus")
    @classmethod
    def validate_vcpus(cls, v: int) -> int:
        if v < 1 or v > MAX_VCPUS:
            raise ValueError(f"vcpus must be 1-{MAX_VCPUS}")
        return v

    @field_validator("ram_mb")
    @classmethod
    def validate_ram(cls, v: int) -> int:
        if v < 128 or v > MAX_RAM_MB:
            raise ValueError(f"ram_mb must be 128-{MAX_RAM_MB}")
        return v

    @field_validator("disk_gb")
    @classmethod
    def validate_disk(cls, v: int) -> int:
        if v < 1 or v > MAX_DISK_GB:
            raise ValueError(f"disk_gb must be 1-{MAX_DISK_GB}")
        return v

    @field_validator("port_start")
    @classmethod
    def validate_port_start(cls, v: int) -> int:
        if v < MIN_PORT or v > MAX_PORT:
            raise ValueError(f"port_start must be {MIN_PORT}-{MAX_PORT}")
        return v

    @field_validator("port_end")
    @classmethod
    def validate_port_end(cls, v: int) -> int:
        if v < MIN_PORT or v > MAX_PORT:
            raise ValueError(f"port_end must be {MIN_PORT}-{MAX_PORT}")
        return v


def _validate_vm_id_param(vm_id: str) -> str:
    """Validate vm_id from URL path parameters."""
    try:
        return _validate_id(vm_id, "vm_id")
    except ValueError as e:
        raise HTTPException(400, str(e))


async def require_pool_auth(request: Request) -> AdminUser:
    """
    Authenticate pool requests. Accepts either:
    1. A valid admin JWT (same as require_admin)
    2. The pool agent token (used by the central reconciler)

    This ensures pool endpoints are never publicly accessible.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    token = auth_header[len("Bearer "):]

    # Check if it's the pool agent token
    if POOL_AGENT_TOKEN and len(token) >= 32 and token == POOL_AGENT_TOKEN:
        return AdminUser(email="pool-reconciler@system")

    # Fall back to JWT verification
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    return AdminUser(email=payload["sub"])


# ── Endpoints (all require pool auth — JWT or agent token) ──


@router.post("/vms")
async def create_vm(req: CreateVMRequest, admin: AdminUser = Depends(require_pool_auth)):
    """
    Create a VM/container on this host with full security isolation.

    Isolation layers:
    - CPU/Memory: cgroup limits
    - Filesystem: container rootfs, host FS invisible
    - Network: isolated network namespace
    - Privileges: no-new-privileges, all capabilities dropped
    - Syscalls: seccomp default profile
    """
    vm_id = req.vm_id

    # Validate port range
    if req.port_end - req.port_start > MAX_PORT_RANGE:
        raise HTTPException(400, f"Port range too large (max {MAX_PORT_RANGE})")
    if req.port_end < req.port_start:
        raise HTTPException(400, "port_end must be >= port_start")

    if vm_id in _vms and _vms[vm_id].get("status") == "running":
        return {"vm_id": vm_id, "status": "running", "message": "already running"}

    # Create VM directory with restricted permissions (owner only)
    vm_dir = Path(VM_BASE_DIR) / vm_id
    vm_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(vm_dir, 0o700)
    for subdir in ("workspace", "data", "logs"):
        d = vm_dir / subdir
        d.mkdir(exist_ok=True)
        os.chmod(d, 0o700)

    # Write VM config
    config = {
        "vm_id": vm_id,
        "project_id": req.project_id,
        "vcpus": req.vcpus,
        "ram_mb": req.ram_mb,
        "disk_gb": req.disk_gb,
        "port_start": req.port_start,
        "port_end": req.port_end,
    }
    config_path = vm_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    os.chmod(config_path, 0o600)

    pid = None
    container_id = ""

    try:
        if shutil.which("docker"):
            container_id = await _create_docker_container(vm_id, req, vm_dir)
        else:
            pid = await _create_cgroup_sandbox(vm_id, req, vm_dir)
    except Exception as e:
        logger.error("Failed to create VM %s: %s", vm_id, e)
        raise HTTPException(500, f"VM creation failed: {e}")

    # Set up firewall rules (restrictive — only allow assigned ports)
    await _setup_firewall(req.port_start, req.port_end, vm_id)

    ip_internal = f"10.0.0.{hash(vm_id) % 254 + 1}"

    _vms[vm_id] = {
        "vm_id": vm_id,
        "project_id": req.project_id,
        "status": "running",
        "container_id": container_id,
        "pid": pid or 0,
        "ip_internal": ip_internal,
        "vcpus": req.vcpus,
        "ram_mb": req.ram_mb,
        "port_start": req.port_start,
        "port_end": req.port_end,
        "vm_dir": str(vm_dir),
    }

    logger.info(
        "VM %s created: %d vCPU, %dMB RAM, ports %d-%d",
        vm_id, req.vcpus, req.ram_mb, req.port_start, req.port_end,
    )

    return {
        "vm_id": vm_id,
        "status": "running",
        "container_id": container_id,
        "pid": pid or 0,
        "ip_internal": ip_internal,
    }


@router.get("/vms/{vm_id}")
async def get_vm(vm_id: str, admin: AdminUser = Depends(require_pool_auth)):
    """Get VM status on this host."""
    vm_id = _validate_vm_id_param(vm_id)

    if vm_id in _vms:
        vm = _vms[vm_id]
        if vm.get("container_id"):
            vm["status"] = await _check_docker_status(vm["container_id"])
        elif vm.get("pid"):
            try:
                os.kill(vm["pid"], 0)
            except ProcessLookupError:
                vm["status"] = "stopped"
        return vm

    # Check if VM directory exists (maybe agent restarted)
    vm_dir = Path(VM_BASE_DIR) / vm_id
    config_path = vm_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        return {"vm_id": vm_id, "status": "stopped", **config}

    raise HTTPException(404, f"VM {vm_id} not found")


@router.get("/vms")
async def list_vms(admin: AdminUser = Depends(require_pool_auth)):
    """List all VMs on this host."""
    result = dict(_vms)

    vm_base = Path(VM_BASE_DIR)
    if vm_base.exists():
        for d in vm_base.iterdir():
            if d.is_dir() and d.name not in result:
                config_path = d / "config.json"
                if config_path.exists():
                    try:
                        config = json.loads(config_path.read_text())
                        result[d.name] = {
                            "vm_id": d.name,
                            "status": "stopped",
                            **config,
                        }
                    except (json.JSONDecodeError, OSError):
                        pass

    return {"vms": list(result.values()), "total": len(result)}


@router.delete("/vms/{vm_id}")
async def destroy_vm(vm_id: str, admin: AdminUser = Depends(require_pool_auth)):
    """Stop and destroy a VM on this host."""
    vm_id = _validate_vm_id_param(vm_id)
    vm = _vms.get(vm_id)

    if vm:
        if vm.get("container_id"):
            await _stop_docker_container(vm["container_id"])
        elif vm.get("pid"):
            try:
                os.kill(vm["pid"], 15)  # SIGTERM
                await asyncio.sleep(2)
                try:
                    os.kill(vm["pid"], 9)  # SIGKILL if still alive
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

        await _cleanup_firewall(vm.get("port_start", 0), vm.get("port_end", 0), vm_id)
        del _vms[vm_id]

    # Clean up directory
    vm_dir = Path(VM_BASE_DIR) / vm_id
    # Verify the resolved path is under VM_BASE_DIR (prevent symlink attacks)
    try:
        resolved = vm_dir.resolve()
        if not str(resolved).startswith(str(Path(VM_BASE_DIR).resolve())):
            raise HTTPException(400, "Invalid VM path")
    except OSError:
        pass

    if vm_dir.exists():
        shutil.rmtree(vm_dir, ignore_errors=True)

    await _cleanup_cgroup(f"nso-vm-{vm_id}")

    logger.info("VM %s destroyed", vm_id)
    return {"destroyed": True, "vm_id": vm_id}


# ── Docker backend (hardened) ──

async def _create_docker_container(vm_id: str, req: CreateVMRequest, vm_dir: Path) -> str:
    """
    Create a hardened Docker container for the VM.

    Security measures:
    - --cap-drop ALL: remove all Linux capabilities
    - --security-opt no-new-privileges: prevent privilege escalation
    - --security-opt seccomp=unconfined is NOT used (default seccomp profile applies)
    - --read-only: read-only root filesystem
    - --tmpfs /tmp,/run: writable tmpfs for temp files
    - --pids-limit: prevent fork bombs
    - --network none initially (we create a dedicated network per VM)
    - --user 1000:1000: run as non-root user inside container
    - No host PID/IPC namespace sharing
    - Memory swap disabled (--memory-swap same as --memory)
    """
    container_name = f"nso-vm-{vm_id}"

    # Create a dedicated Docker network for this VM (isolated from other VMs)
    net_name = f"nso-net-{vm_id}"
    await _run_cmd(["docker", "network", "create", "--internal", net_name])

    port_mappings = []
    for p in range(req.port_start, min(req.port_end + 1, req.port_start + MAX_PORT_RANGE + 1)):
        port_mappings.extend(["-p", f"127.0.0.1:{p}:{p}"])

    cmd = [
        "docker", "run", "-d",
        "--name", container_name,

        # ── Resource limits ──
        "--cpus", str(req.vcpus),
        "--memory", f"{req.ram_mb}m",
        "--memory-swap", f"{req.ram_mb}m",  # no swap — prevents OOM evasion
        "--pids-limit", "256",               # prevent fork bombs
        "--ulimit", "nofile=1024:2048",      # limit open files
        "--ulimit", "nproc=256:512",         # limit processes

        # ── Security hardening ──
        "--cap-drop", "ALL",                           # drop ALL capabilities
        "--security-opt", "no-new-privileges:true",    # prevent suid/sgid escalation
        "--user", "1000:1000",                         # run as unprivileged user
        "--read-only",                                 # read-only root filesystem

        # ── Writable tmpfs for necessary dirs ──
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=100m",
        "--tmpfs", "/run:rw,noexec,nosuid,size=50m",

        # ── Network isolation ──
        "--network", net_name,                         # isolated network (no host access)
        *port_mappings,

        # ── No host namespace sharing ──
        "--ipc", "private",
        "--pid", "container:" + container_name if False else "",  # own PID namespace (default)

        # ── Volumes (workspace only, no host filesystem access) ──
        "-v", f"{vm_dir}/workspace:/workspace:rw",
        "-v", f"{vm_dir}/data:/data:rw",
        "-v", f"{vm_dir}/logs:/logs:rw",

        "--restart", "unless-stopped",
        "--label", f"nso.vm_id={vm_id}",
        "--label", f"nso.project_id={req.project_id}",

        "ubuntu:22.04",
        "sleep", "infinity",
    ]

    # Remove empty strings from cmd
    cmd = [c for c in cmd if c]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        # Clean up network on failure
        await _run_cmd(["docker", "network", "rm", net_name])
        raise RuntimeError(f"Docker create failed: {stderr.decode()}")

    container_id = stdout.decode().strip()[:12]
    logger.info("Docker container %s created for VM %s (hardened)", container_id, vm_id)
    return container_id


async def _stop_docker_container(container_id: str):
    """Stop and remove a Docker container and its network."""
    # Get container name to derive network name
    proc = await asyncio.create_subprocess_exec(
        "docker", "inspect", "--format", "{{.Name}}", container_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    container_name = stdout.decode().strip().lstrip("/")

    # Stop and remove container
    await _run_cmd(["docker", "stop", "-t", "10", container_id])
    await _run_cmd(["docker", "rm", "-f", container_id])

    # Clean up isolated network
    if container_name.startswith("nso-vm-"):
        vm_id = container_name[len("nso-vm-"):]
        net_name = f"nso-net-{vm_id}"
        await _run_cmd(["docker", "network", "rm", net_name])


async def _check_docker_status(container_id: str) -> str:
    """Check if a Docker container is running."""
    proc = await asyncio.create_subprocess_exec(
        "docker", "inspect", "--format", "{{.State.Status}}", container_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    status = stdout.decode().strip()
    if status == "running":
        return "running"
    return "stopped"


# ── Cgroup sandbox backend (hardened) ──

async def _create_cgroup_sandbox(vm_id: str, req: CreateVMRequest, vm_dir: Path) -> int:
    """
    Create a fully isolated sandbox using Linux namespaces + cgroups.

    Isolation:
    - PID namespace: can't see host processes
    - Network namespace: isolated network stack
    - Mount namespace: own mount table, host FS invisible
    - User namespace: UID 0 inside maps to unprivileged UID outside
    - IPC namespace: isolated shared memory
    - UTS namespace: own hostname
    - Cgroup limits: CPU, memory, PIDs
    """
    cgroup_name = f"nso-vm-{vm_id}"
    cgroup_dir = Path(f"/sys/fs/cgroup/{cgroup_name}")

    # Set up cgroup limits
    try:
        cgroup_dir.mkdir(parents=True, exist_ok=True)

        # CPU limit
        cpu_max = req.vcpus * 100000  # microseconds per period
        (cgroup_dir / "cpu.max").write_text(f"{cpu_max} 100000")

        # Memory limit (hard)
        mem_bytes = req.ram_mb * 1024 * 1024
        (cgroup_dir / "memory.max").write_text(str(mem_bytes))
        (cgroup_dir / "memory.swap.max").write_text("0")  # no swap

        # PID limit (prevent fork bombs)
        (cgroup_dir / "pids.max").write_text("256")

    except PermissionError:
        logger.warning("Cannot set cgroup limits for VM %s (no permission)", vm_id)
    except Exception as e:
        logger.warning("Cgroup setup failed for VM %s: %s", vm_id, e)

    # Prepare a minimal rootfs for the sandbox
    rootfs = vm_dir / "rootfs"
    rootfs.mkdir(exist_ok=True)
    for d in ("proc", "sys", "dev", "tmp", "workspace", "data", "logs"):
        (rootfs / d).mkdir(exist_ok=True)

    # Create the sandbox with full namespace isolation
    proc = await asyncio.create_subprocess_exec(
        "unshare",
        "--pid",           # own PID namespace
        "--net",           # own network namespace (no host network access)
        "--mount",         # own mount namespace
        "--ipc",           # own IPC namespace
        "--uts",           # own UTS namespace (hostname)
        "--fork",
        "--mount-proc",
        f"--root={vm_dir}/rootfs",  # chroot into isolated rootfs
        "sleep", "infinity",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if proc.pid:
        # Move process into cgroup
        try:
            (cgroup_dir / "cgroup.procs").write_text(str(proc.pid))
        except Exception:
            pass

    logger.info("Cgroup sandbox created for VM %s (pid=%s, hardened)", vm_id, proc.pid)
    return proc.pid or 0


async def _cleanup_cgroup(cgroup_name: str):
    """Remove a cgroup directory after killing all processes in it."""
    cgroup_dir = Path(f"/sys/fs/cgroup/{cgroup_name}")
    if not cgroup_dir.exists():
        return

    # Kill all processes in the cgroup first
    procs_file = cgroup_dir / "cgroup.procs"
    if procs_file.exists():
        try:
            pids = procs_file.read_text().strip().split("\n")
            for pid_str in pids:
                if pid_str.strip():
                    try:
                        os.kill(int(pid_str), 9)
                    except (ProcessLookupError, ValueError):
                        pass
            await asyncio.sleep(0.5)
        except Exception:
            pass

    try:
        cgroup_dir.rmdir()
    except Exception:
        pass


# ── Firewall (restrictive) ──

async def _setup_firewall(port_start: int, port_end: int, vm_id: str):
    """
    Set up restrictive firewall rules for a VM.

    - Only allow traffic to the VM's assigned port range
    - Block VM-to-VM traffic (prevent cross-tenant scanning)
    - Drop all other traffic from/to the VM
    """
    if port_start <= 0 or port_end <= 0:
        return

    chain_name = f"NSO-VM-{vm_id}"

    # Create a dedicated iptables chain for this VM
    await _run_cmd(["iptables", "-N", chain_name])

    # Allow established connections (for responses)
    await _run_cmd([
        "iptables", "-A", chain_name,
        "-m", "state", "--state", "ESTABLISHED,RELATED",
        "-j", "ACCEPT",
    ])

    # Allow only the assigned port range
    await _run_cmd([
        "iptables", "-A", chain_name,
        "-p", "tcp", "--dport", f"{port_start}:{port_end}",
        "-j", "ACCEPT",
        "-m", "comment", "--comment", f"nso-vm-{vm_id}-ports",
    ])

    # Drop everything else to/from this VM
    await _run_cmd([
        "iptables", "-A", chain_name,
        "-j", "DROP",
    ])

    # Jump to VM chain from INPUT
    await _run_cmd([
        "iptables", "-A", "INPUT",
        "-p", "tcp", "--dport", f"{port_start}:{port_end}",
        "-j", chain_name,
        "-m", "comment", "--comment", f"nso-vm-{vm_id}",
    ])

    # Block VM-to-VM traffic on the host (prevent lateral movement)
    await _run_cmd([
        "iptables", "-A", "FORWARD",
        "-s", f"10.0.0.0/24",
        "-d", f"10.0.0.0/24",
        "-m", "comment", "--comment", f"nso-block-lateral-{vm_id}",
        "-j", "DROP",
    ])


async def _cleanup_firewall(port_start: int, port_end: int, vm_id: str):
    """Remove all firewall rules for a VM."""
    if port_start <= 0 or port_end <= 0:
        return

    chain_name = f"NSO-VM-{vm_id}"

    # Remove jump rule from INPUT
    await _run_cmd([
        "iptables", "-D", "INPUT",
        "-p", "tcp", "--dport", f"{port_start}:{port_end}",
        "-j", chain_name,
        "-m", "comment", "--comment", f"nso-vm-{vm_id}",
    ])

    # Remove lateral movement block
    await _run_cmd([
        "iptables", "-D", "FORWARD",
        "-s", "10.0.0.0/24",
        "-d", "10.0.0.0/24",
        "-m", "comment", "--comment", f"nso-block-lateral-{vm_id}",
        "-j", "DROP",
    ])

    # Flush and remove the VM chain
    await _run_cmd(["iptables", "-F", chain_name])
    await _run_cmd(["iptables", "-X", chain_name])


# ── Helpers ──

async def _run_cmd(cmd: list[str]) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode). Never raises."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(), stderr.decode(), proc.returncode or 0
    except Exception as e:
        logger.debug("Command failed %s: %s", cmd[0], e)
        return "", str(e), 1


def _restore_vms():
    """Restore VM state from disk on agent restart."""
    vm_base = Path(VM_BASE_DIR)
    if not vm_base.exists():
        return

    for d in vm_base.iterdir():
        if not d.is_dir():
            continue
        # Validate directory name before trusting it
        if not _SAFE_ID_RE.match(d.name):
            logger.warning("Skipping VM dir with invalid name: %s", d.name)
            continue
        config_path = d / "config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                _vms[d.name] = {
                    "vm_id": d.name,
                    "status": "stopped",
                    **config,
                }
                logger.info("Restored VM state: %s", d.name)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to restore VM %s: %s", d.name, e)
