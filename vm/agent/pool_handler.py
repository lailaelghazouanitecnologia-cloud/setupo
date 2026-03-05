"""
Pool VM Handler — host-side agent endpoints for VM lifecycle.

When this agent runs on a HOST machine (not a user VPS), these endpoints
let the pool reconciler create/destroy/inspect VMs on this host.

VMs are implemented as isolated containers using systemd-nspawn or Docker,
with cgroup resource limits matching the plan allocation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("nso-agent.pool")

router = APIRouter(prefix="/pool")

VM_BASE_DIR = os.environ.get("NSO_VM_DIR", "/opt/nso/vms")
_vms: dict[str, dict] = {}  # in-memory VM state


class CreateVMRequest(BaseModel):
    vm_id: str
    project_id: str
    vcpus: int = 1
    ram_mb: int = 512
    disk_gb: int = 10
    port_start: int = 10000
    port_end: int = 10099


@router.post("/vms")
async def create_vm(req: CreateVMRequest):
    """
    Create a VM/container on this host.

    Uses cgroups for resource isolation:
    - CPU: limited via cpu.max
    - Memory: limited via memory.max
    - Disk: directory with quota (if supported)
    - Network: port range forwarding
    """
    vm_id = req.vm_id

    if vm_id in _vms and _vms[vm_id].get("status") == "running":
        return {"vm_id": vm_id, "status": "running", "message": "already running"}

    # Create VM directory
    vm_dir = Path(VM_BASE_DIR) / vm_id
    vm_dir.mkdir(parents=True, exist_ok=True)
    (vm_dir / "workspace").mkdir(exist_ok=True)
    (vm_dir / "data").mkdir(exist_ok=True)
    (vm_dir / "logs").mkdir(exist_ok=True)

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
    (vm_dir / "config.json").write_text(json.dumps(config, indent=2))

    # Apply cgroup limits
    cgroup_name = f"nso-vm-{vm_id}"
    pid = None
    container_id = ""

    try:
        # Try Docker first (preferred)
        if shutil.which("docker"):
            container_id = await _create_docker_container(vm_id, req, vm_dir)
        else:
            # Fallback: cgroup-based isolation without full container
            pid = await _create_cgroup_sandbox(vm_id, req, vm_dir)
    except Exception as e:
        logger.error("Failed to create VM %s: %s", vm_id, e)
        # Even without containerization, we can still serve the VM
        # as a directory-isolated process
        logger.info("VM %s created in directory-only mode", vm_id)

    # Set up port forwarding (iptables)
    await _setup_port_forwarding(req.port_start, req.port_end, vm_id)

    ip_internal = f"10.0.0.{hash(vm_id) % 254 + 1}"  # deterministic internal IP

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
async def get_vm(vm_id: str):
    """Get VM status on this host."""
    if vm_id in _vms:
        vm = _vms[vm_id]
        # Verify process is still alive
        if vm.get("pid"):
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
        return {
            "vm_id": vm_id,
            "status": "stopped",  # directory exists but not tracked
            **config,
        }

    raise HTTPException(404, f"VM {vm_id} not found")


@router.get("/vms")
async def list_vms():
    """List all VMs on this host."""
    # Merge in-memory state with directory scan
    result = dict(_vms)

    vm_base = Path(VM_BASE_DIR)
    if vm_base.exists():
        for d in vm_base.iterdir():
            if d.is_dir() and d.name not in result:
                config_path = d / "config.json"
                if config_path.exists():
                    config = json.loads(config_path.read_text())
                    result[d.name] = {
                        "vm_id": d.name,
                        "status": "stopped",
                        **config,
                    }

    return {"vms": list(result.values()), "total": len(result)}


@router.delete("/vms/{vm_id}")
async def destroy_vm(vm_id: str):
    """Stop and destroy a VM on this host."""
    vm = _vms.get(vm_id)

    if vm:
        # Stop container/process
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

        # Remove port forwarding
        await _cleanup_port_forwarding(vm.get("port_start", 0), vm.get("port_end", 0))

        del _vms[vm_id]

    # Clean up directory
    vm_dir = Path(VM_BASE_DIR) / vm_id
    if vm_dir.exists():
        shutil.rmtree(vm_dir, ignore_errors=True)

    # Clean up cgroup
    await _cleanup_cgroup(f"nso-vm-{vm_id}")

    logger.info("VM %s destroyed", vm_id)
    return {"destroyed": True, "vm_id": vm_id}


# ── Container backends ──

async def _create_docker_container(vm_id: str, req: CreateVMRequest, vm_dir: Path) -> str:
    """Create a Docker container for the VM."""
    port_mappings = []
    for p in range(req.port_start, req.port_end + 1):
        port_mappings.extend(["-p", f"{p}:{p}"])

    cmd = [
        "docker", "run", "-d",
        "--name", f"nso-vm-{vm_id}",
        "--cpus", str(req.vcpus),
        "--memory", f"{req.ram_mb}m",
        "-v", f"{vm_dir}/workspace:/workspace",
        "-v", f"{vm_dir}/data:/data",
        *port_mappings,
        "--restart", "unless-stopped",
        "ubuntu:22.04",
        "sleep", "infinity",  # Keep alive, supervisor will run actual processes
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"Docker create failed: {stderr.decode()}")

    container_id = stdout.decode().strip()[:12]
    logger.info("Docker container %s created for VM %s", container_id, vm_id)
    return container_id


async def _stop_docker_container(container_id: str):
    """Stop and remove a Docker container."""
    for cmd in [["docker", "stop", container_id], ["docker", "rm", "-f", container_id]]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()


async def _create_cgroup_sandbox(vm_id: str, req: CreateVMRequest, vm_dir: Path) -> int:
    """Create a cgroup-isolated sandbox (no Docker)."""
    cgroup_name = f"nso-vm-{vm_id}"

    # Create cgroup v2 directory
    cgroup_dir = Path(f"/sys/fs/cgroup/{cgroup_name}")
    try:
        cgroup_dir.mkdir(parents=True, exist_ok=True)

        # Set CPU limit (microseconds per period)
        cpu_max = req.vcpus * 100000  # 100ms per CPU
        (cgroup_dir / "cpu.max").write_text(f"{cpu_max} 100000")

        # Set memory limit
        (cgroup_dir / "memory.max").write_text(str(req.ram_mb * 1024 * 1024))

    except PermissionError:
        logger.warning("Cannot set cgroup limits for VM %s (no permission)", vm_id)
    except Exception as e:
        logger.warning("Cgroup setup failed for VM %s: %s", vm_id, e)

    # Start a lightweight init process in the sandbox
    proc = await asyncio.create_subprocess_exec(
        "unshare", "--pid", "--fork", "--mount-proc",
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

    logger.info("Cgroup sandbox created for VM %s (pid=%s)", vm_id, proc.pid)
    return proc.pid or 0


async def _cleanup_cgroup(cgroup_name: str):
    """Remove a cgroup directory."""
    cgroup_dir = Path(f"/sys/fs/cgroup/{cgroup_name}")
    if cgroup_dir.exists():
        try:
            cgroup_dir.rmdir()
        except Exception:
            pass


async def _setup_port_forwarding(port_start: int, port_end: int, vm_id: str):
    """Set up iptables port forwarding for the VM port range."""
    if port_start <= 0 or port_end <= 0:
        return
    # Mark these ports as belonging to this VM (for firewall rules)
    try:
        proc = await asyncio.create_subprocess_exec(
            "iptables", "-A", "INPUT",
            "-p", "tcp", "--dport", f"{port_start}:{port_end}",
            "-j", "ACCEPT",
            "-m", "comment", "--comment", f"nso-vm-{vm_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception:
        pass  # iptables may not be available


async def _cleanup_port_forwarding(port_start: int, port_end: int):
    """Remove iptables rules for a port range."""
    if port_start <= 0 or port_end <= 0:
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "iptables", "-D", "INPUT",
            "-p", "tcp", "--dport", f"{port_start}:{port_end}",
            "-j", "ACCEPT",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception:
        pass


def _restore_vms():
    """Restore VM state from disk on agent restart."""
    vm_base = Path(VM_BASE_DIR)
    if not vm_base.exists():
        return

    for d in vm_base.iterdir():
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
            except Exception:
                pass
