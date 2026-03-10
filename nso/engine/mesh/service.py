"""
NSO Mesh — Device management via SSH proxy.

Central server maintains SSH connections to registered devices
and proxies all operations (exec, deploy, files) through them.
"""

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime
from pathlib import Path

from nso.config import settings
from nso.shared import db
from nso.shared.errors import NsoError
from nso.engine.compute.provisioner import (
    run_ssh_command,
    scp_upload,
    wait_for_ssh,
)

logger = logging.getLogger("nso.mesh")

MESH_KEYS_DIR = settings.DATA_DIR / "mesh"


# ── SSH key management ──────────────────────────────────────────


def _master_key_path() -> Path:
    MESH_KEYS_DIR.mkdir(parents=True, exist_ok=True)
    return MESH_KEYS_DIR / "master_key"


def _master_pubkey_path() -> Path:
    return _master_key_path().with_suffix(".pub")


async def ensure_master_key() -> str:
    """Generate master ed25519 keypair if it doesn't exist. Returns public key."""
    key_path = _master_key_path()
    pub_path = _master_pubkey_path()
    if key_path.exists() and pub_path.exists():
        return pub_path.read_text().strip()

    MESH_KEYS_DIR.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ssh-keygen", "-t", "ed25519", "-f", str(key_path),
        "-N", "", "-C", "nso-mesh-central",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode != 0:
        raise NsoError("Failed to generate mesh SSH keypair", 500)
    key_path.chmod(0o600)
    logger.info("Generated mesh master SSH keypair at %s", key_path)
    return pub_path.read_text().strip()


def get_master_key_path() -> str:
    """Return path to private key for SSH commands."""
    return str(_master_key_path())


# ── Device CRUD ─────────────────────────────────────────────────


def _gen_device_id() -> str:
    return f"dev_{secrets.token_hex(8)}"


def _gen_install_token() -> str:
    return f"dtk_{secrets.token_hex(16)}"


def _gen_group_id() -> str:
    return f"grp_{secrets.token_hex(8)}"


def _gen_operation_id() -> str:
    return f"op_{secrets.token_hex(8)}"


async def register_device(project_id: str, name: str, host: str,
                           ssh_port: int = 22, ssh_user: str = "root",
                           tags: list[str] | None = None,
                           metadata: dict | None = None) -> dict:
    """Register a new device. Returns device record with install_token."""
    # Check uniqueness
    existing = await db.fetch_one("mesh_devices", project_id=project_id, name=name)
    if existing:
        raise NsoError(f"Device '{name}' already exists in this project", 409)

    device_id = _gen_device_id()
    install_token = _gen_install_token()

    await db.insert("mesh_devices", {
        "id": device_id,
        "project_id": project_id,
        "name": name,
        "host": host,
        "ssh_port": ssh_port,
        "ssh_user": ssh_user,
        "status": "pending",
        "install_token": install_token,
        "tags": tags or [],
        "metadata": metadata or {},
    })

    device = await db.fetch_one("mesh_devices", id=device_id)
    logger.info("Registered mesh device %s (%s) for project %s", name, host, project_id)
    return device


async def activate_device(device_id: str, token: str,
                          fingerprint: str = "", os_info: str = "",
                          agent_version: str = "") -> dict:
    """Activate a device after bootstrap script runs. Validates one-time token."""
    device = await db.fetch_one("mesh_devices", id=device_id)
    if not device:
        raise NsoError("Device not found", 404)
    if device["install_token"] != token:
        raise NsoError("Invalid install token", 403)
    if device["status"] not in ("pending", "provisioning", "error"):
        raise NsoError(f"Device already activated (status={device['status']})", 400)

    # Verify SSH connectivity
    key_path = get_master_key_path()
    reachable = await wait_for_ssh(device["host"], device["ssh_port"], timeout=30)
    if not reachable:
        await db.update("mesh_devices", device_id, {
            "status": "error",
            "updated_at": datetime.utcnow().isoformat(),
        })
        raise NsoError("Cannot reach device via SSH", 502)

    # Test SSH command
    output, code = await run_ssh_command(
        device["host"], "echo ok", key_path,
        user=device["ssh_user"],
    )
    if code != 0:
        await db.update("mesh_devices", device_id, {
            "status": "error",
            "updated_at": datetime.utcnow().isoformat(),
        })
        raise NsoError(f"SSH test failed: {output}", 502)

    os_data = {}
    if os_info:
        os_data["uname"] = os_info

    now = datetime.utcnow().isoformat()
    await db.update("mesh_devices", device_id, {
        "status": "online",
        "install_token": "",
        "ssh_fingerprint": fingerprint,
        "os_info": os_data,
        "agent_version": agent_version,
        "last_seen_at": now,
        "updated_at": now,
    })

    logger.info("Activated mesh device %s (%s)", device["name"], device["host"])
    return await db.fetch_one("mesh_devices", id=device_id)


async def get_device(project_id: str, device_id: str) -> dict:
    device = await db.fetch_one("mesh_devices", id=device_id)
    if not device or device["project_id"] != project_id:
        raise NsoError("Device not found", 404)
    return device


async def list_devices(project_id: str, status: str | None = None,
                       tag: str | None = None) -> list[dict]:
    devices = await db.fetch_all("mesh_devices", project_id=project_id)
    if status:
        devices = [d for d in devices if d["status"] == status]
    if tag:
        devices = [d for d in devices if tag in (d.get("tags") or [])]
    return devices


async def update_device(project_id: str, device_id: str, data: dict) -> dict:
    device = await get_device(project_id, device_id)
    update_data = {k: v for k, v in data.items() if v is not None}
    if not update_data:
        return device
    update_data["updated_at"] = datetime.utcnow().isoformat()
    await db.update("mesh_devices", device_id, update_data)
    return await db.fetch_one("mesh_devices", id=device_id)


async def delete_device(project_id: str, device_id: str):
    await get_device(project_id, device_id)
    await db.delete("mesh_devices", device_id)
    logger.info("Deleted mesh device %s from project %s", device_id, project_id)


# ── SSH Operations ──────────────────────────────────────────────


async def exec_on_device(project_id: str, device_id: str,
                         command: str, timeout: int = 60,
                         triggered_by: str = "system") -> dict:
    """Execute a command on a device via SSH. Returns operation record."""
    device = await get_device(project_id, device_id)
    if device["status"] != "online":
        raise NsoError(f"Device is {device['status']}, must be online", 400)

    key_path = get_master_key_path()
    start = time.monotonic()

    output, exit_code = await run_ssh_command(
        device["host"], command, key_path,
        user=device["ssh_user"], timeout=timeout,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    op_id = _gen_operation_id()
    await db.insert("mesh_operations", {
        "id": op_id,
        "device_id": device_id,
        "operation": "exec",
        "command": command,
        "exit_code": exit_code,
        "stdout": output,
        "stderr": "",
        "duration_ms": duration_ms,
        "triggered_by": triggered_by,
    })

    return {
        "operation_id": op_id,
        "device_id": device_id,
        "command": command,
        "output": output,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    }


async def get_device_status(project_id: str, device_id: str) -> dict:
    """Get live status of a device by running health check via SSH."""
    device = await get_device(project_id, device_id)
    if device["status"] != "online":
        return {"device": device, "live": False}

    key_path = get_master_key_path()
    # Collect basic metrics
    cmd = "echo ok && cat /proc/loadavg && free -m | head -2 && df -h / | tail -1"
    output, code = await run_ssh_command(
        device["host"], cmd, key_path,
        user=device["ssh_user"], timeout=10,
    )

    return {
        "device": device,
        "live": code == 0,
        "raw_metrics": output if code == 0 else None,
    }


async def deploy_to_device(project_id: str, device_id: str,
                           zar_path: str, target_dir: str = "/opt/app") -> dict:
    """Deploy a .zar file to a device via SCP + SSH."""
    import re
    import shlex

    device = await get_device(project_id, device_id)
    if device["status"] != "online":
        raise NsoError(f"Device is {device['status']}, must be online", 400)

    # Validate target_dir to prevent command injection
    if not re.match(r"^/[a-zA-Z0-9/_.-]+$", target_dir) or ".." in target_dir:
        raise NsoError(f"Invalid target directory: {target_dir}", 400)
    if target_dir in ("/", "/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys"):
        raise NsoError(f"Cannot deploy to system directory: {target_dir}", 400)

    key_path = get_master_key_path()
    start = time.monotonic()

    # Upload .zar — use 8 bytes for stronger randomness
    remote_zar = f"/tmp/deploy-{secrets.token_hex(8)}.zar"
    uploaded = await scp_upload(
        device["host"], zar_path, remote_zar, key_path,
        user=device["ssh_user"],
    )
    if not uploaded:
        raise NsoError("Failed to upload .zar to device", 502)

    # Extract and deploy — use shlex.quote for safety
    safe_target = shlex.quote(target_dir)
    safe_zar = shlex.quote(remote_zar)
    deploy_cmd = (
        f"mkdir -p {safe_target} && "
        f"tar xzf {safe_zar} -C {safe_target} && "
        f"rm -f {safe_zar}"
    )
    output, code = await run_ssh_command(
        device["host"], deploy_cmd, key_path,
        user=device["ssh_user"], timeout=120,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    op_id = _gen_operation_id()
    await db.insert("mesh_operations", {
        "id": op_id,
        "device_id": device_id,
        "operation": "deploy",
        "command": f"deploy {zar_path} → {target_dir}",
        "exit_code": code,
        "stdout": output,
        "stderr": "",
        "duration_ms": duration_ms,
        "triggered_by": "user",
    })

    if code != 0:
        raise NsoError(f"Deploy failed: {output}", 502)

    return {
        "operation_id": op_id,
        "device_id": device_id,
        "exit_code": code,
        "output": output,
        "duration_ms": duration_ms,
    }


async def list_device_files(project_id: str, device_id: str,
                            path: str = "/") -> dict:
    """List files on a device via SSH."""
    result = await exec_on_device(
        project_id, device_id,
        f"ls -la {path}",
        triggered_by="system",
    )
    return result


async def read_device_file(project_id: str, device_id: str,
                           path: str) -> dict:
    """Read a file from a device via SSH."""
    result = await exec_on_device(
        project_id, device_id,
        f"cat {path}",
        triggered_by="system",
    )
    return result


async def write_device_file(project_id: str, device_id: str,
                            path: str, content: str) -> dict:
    """Write a file to a device via SSH."""
    import re
    import shlex

    # Validate path to prevent injection
    if not re.match(r"^/[a-zA-Z0-9/_.-]+$", path) or ".." in path:
        raise NsoError(f"Invalid file path: {path}", 400)

    # Use heredoc with quoted delimiter (prevents variable expansion)
    safe_path = shlex.quote(path)
    # Replace NSOEOF in content to prevent heredoc escape
    safe_content = content.replace("NSOEOF", "NSO_EOF")
    result = await exec_on_device(
        project_id, device_id,
        f"cat > {safe_path} << 'NSOEOF'\n{safe_content}\nNSOEOF",
        triggered_by="user",
    )
    return result


async def get_device_logs(project_id: str, device_id: str,
                          limit: int = 50) -> list[dict]:
    """Get recent operations for a device."""
    await get_device(project_id, device_id)
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM mesh_operations WHERE device_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (device_id, limit),
    )
    rows = await cursor.fetchall()
    return [db.row_to_dict(r) for r in rows]


# ── Group operations ────────────────────────────────────────────


async def create_group(project_id: str, name: str,
                       description: str = "") -> dict:
    existing = await db.fetch_one("mesh_groups", project_id=project_id, name=name)
    if existing:
        raise NsoError(f"Group '{name}' already exists", 409)

    group_id = _gen_group_id()
    await db.insert("mesh_groups", {
        "id": group_id,
        "project_id": project_id,
        "name": name,
        "description": description,
    })
    return await db.fetch_one("mesh_groups", id=group_id)


async def list_groups(project_id: str) -> list[dict]:
    groups = await db.fetch_all("mesh_groups", project_id=project_id)
    for group in groups:
        conn = await db.get_db()
        cursor = await conn.execute(
            "SELECT device_id FROM mesh_device_groups WHERE group_id = ?",
            (group["id"],),
        )
        rows = await cursor.fetchall()
        group["device_ids"] = [r["device_id"] for r in rows]
    return groups


async def get_group(project_id: str, group_id: str) -> dict:
    group = await db.fetch_one("mesh_groups", id=group_id)
    if not group or group["project_id"] != project_id:
        raise NsoError("Group not found", 404)
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT device_id FROM mesh_device_groups WHERE group_id = ?",
        (group_id,),
    )
    rows = await cursor.fetchall()
    group["device_ids"] = [r["device_id"] for r in rows]
    return group


async def update_group(project_id: str, group_id: str, data: dict) -> dict:
    await get_group(project_id, group_id)
    update_data = {k: v for k, v in data.items() if v is not None}
    if update_data:
        await db.update("mesh_groups", group_id, update_data)
    return await get_group(project_id, group_id)


async def delete_group(project_id: str, group_id: str):
    await get_group(project_id, group_id)
    await db.delete("mesh_groups", group_id)


async def add_devices_to_group(project_id: str, group_id: str,
                               device_ids: list[str]):
    await get_group(project_id, group_id)
    conn = await db.get_db()
    for did in device_ids:
        await get_device(project_id, did)
        await conn.execute(
            "INSERT INTO mesh_device_groups (device_id, group_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (did, group_id),
        )
    await conn.commit()


async def remove_device_from_group(project_id: str, group_id: str,
                                   device_id: str):
    await get_group(project_id, group_id)
    await db.delete_where("mesh_device_groups", device_id=device_id, group_id=group_id)


async def exec_on_group(project_id: str, group_id: str,
                        command: str, timeout: int = 60,
                        triggered_by: str = "user") -> list[dict]:
    """Execute a command on all devices in a group concurrently."""
    group = await get_group(project_id, group_id)
    device_ids = group.get("device_ids", [])
    if not device_ids:
        return []

    tasks = [
        exec_on_device(project_id, did, command, timeout, triggered_by)
        for did in device_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for did, result in zip(device_ids, results):
        if isinstance(result, Exception):
            output.append({
                "device_id": did,
                "error": str(result),
                "exit_code": -1,
            })
        else:
            output.append(result)
    return output


async def group_status(project_id: str, group_id: str) -> dict:
    """Get aggregated status for all devices in a group."""
    group = await get_group(project_id, group_id)
    device_ids = group.get("device_ids", [])

    devices = []
    for did in device_ids:
        try:
            status = await get_device_status(project_id, did)
            devices.append(status)
        except NsoError:
            devices.append({"device_id": did, "live": False})

    online = sum(1 for d in devices if d.get("live"))
    return {
        "group": group,
        "total": len(devices),
        "online": online,
        "offline": len(devices) - online,
        "devices": devices,
    }
