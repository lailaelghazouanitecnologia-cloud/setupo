"""
Mesh tools — manage external devices and groups from the deploy agent.

Tools:
  - list_mesh_devices: List all registered mesh devices
  - list_mesh_groups: List device groups
  - register_mesh_device: Register a new external server
  - exec_on_mesh_device: Run command on a device via SSH
  - exec_on_mesh_group: Run command on all devices in a group concurrently
  - deploy_to_mesh: Deploy a workspace .zar to a device or group
  - mesh_device_status: Get live health and metrics for a device
  - manage_mesh_group: Create group, add/remove devices
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from typing import TYPE_CHECKING

from nso.shared import db
from nso.config import settings

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext

logger = logging.getLogger("nso.deploy_agent.tools.mesh")


def create_mesh_tools(ctx: DeployContext) -> list[tuple]:
    """Create mesh management tools bound to project context."""

    async def list_mesh_devices(status: str = "", tag: str = "") -> str:
        """List all registered mesh devices for this project. Shows external servers (Hetzner, OVH, Raspberry Pi, etc.)
        managed via SSH. Filter by status (online/offline/pending) or tag."""
        from nso.engine.mesh.service import list_devices

        try:
            devices = await list_devices(ctx.project_id, status=status or None, tag=tag or None)
        except Exception as e:
            return json.dumps({"error": str(e)})

        result = []
        for d in devices:
            result.append({
                "id": d["id"],
                "name": d.get("name", ""),
                "host": d.get("host", ""),
                "ssh_port": d.get("ssh_port", 22),
                "status": d.get("status", "unknown"),
                "last_seen": d.get("last_seen_at", ""),
                "tags": d.get("tags", []),
                "os_info": d.get("os_info", {}),
            })

        return json.dumps({
            "devices": result,
            "count": len(result),
            "online": sum(1 for d in result if d["status"] == "online"),
            "hint": "These are external servers managed via SSH. Use exec_on_mesh_device to run commands, "
                    "or deploy_to_mesh to deploy a workspace.",
        })

    async def list_mesh_groups() -> str:
        """List all mesh device groups. Groups allow batch operations across multiple servers."""
        from nso.engine.mesh.service import list_groups

        try:
            groups = await list_groups(ctx.project_id)
        except Exception as e:
            return json.dumps({"error": str(e)})

        result = []
        for g in groups:
            result.append({
                "id": g["id"],
                "name": g.get("name", ""),
                "description": g.get("description", ""),
                "device_count": len(g.get("device_ids", [])),
                "device_ids": g.get("device_ids", []),
            })

        return json.dumps({"groups": result, "count": len(result)})

    async def register_mesh_device(
        name: str,
        host: str,
        ssh_port: int = 22,
        ssh_user: str = "root",
        tags: str = "",
    ) -> str:
        """Register a new external server (Hetzner, OVH, DigitalOcean, Raspberry Pi, bare metal, etc.).
        After registration, the user must run the install script on the device to activate it.
        tags: comma-separated list (e.g. 'production,eu-west')."""
        from nso.engine.mesh.service import register_device

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        try:
            device = await register_device(
                project_id=ctx.project_id,
                name=name,
                host=host,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                tags=tag_list,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

        install_token = device.get("install_token", "")
        base_url = os.environ.get("NSO_PUBLIC_URL", "https://nso.dev")
        install_url = f"{base_url}/api/projects/{ctx.project_id}/mesh/install/{install_token}"

        return json.dumps({
            "ok": True,
            "device_id": device["id"],
            "name": name,
            "host": host,
            "status": "pending",
            "install_command": f"curl -fsSL {install_url} | bash",
            "message": f"Device '{name}' registered. Run the install command on the server to activate it.",
        })

    async def exec_on_mesh_device(device_id: str, command: str, timeout: int = 60) -> str:
        """Execute a command on a mesh device via SSH. The device must be online.
        Use this for remote operations: checking logs, restarting services, running scripts, etc."""
        from nso.engine.mesh.service import exec_on_device

        try:
            result = await exec_on_device(
                project_id=ctx.project_id,
                device_id=device_id,
                command=command,
                timeout=timeout,
                triggered_by="deploy_agent",
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps({
            "ok": result.get("exit_code", -1) == 0,
            "device_id": device_id,
            "command": command,
            "output": result.get("output", ""),
            "exit_code": result.get("exit_code", -1),
            "duration_ms": result.get("duration_ms", 0),
        })

    async def exec_on_mesh_group(group_id: str, command: str, timeout: int = 60) -> str:
        """Execute a command on ALL devices in a mesh group concurrently.
        Perfect for rolling updates, health checks, or batch operations across servers."""
        from nso.engine.mesh.service import exec_on_group

        try:
            results = await exec_on_group(
                project_id=ctx.project_id,
                group_id=group_id,
                command=command,
                timeout=timeout,
                triggered_by="deploy_agent",
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

        succeeded = sum(1 for r in results if r.get("exit_code", -1) == 0)
        failed = len(results) - succeeded

        return json.dumps({
            "ok": failed == 0,
            "group_id": group_id,
            "command": command,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        })

    async def deploy_to_mesh(
        workspace: str,
        target: str = "",
        target_dir: str = "/opt/app",
        branch: str = "main",
        restart_command: str = "",
    ) -> str:
        """Deploy a workspace to mesh devices. Can target a single device (dev_xxx) or an entire group (grp_xxx).
        Packs workspace as .zar, uploads via SCP, extracts on target, optionally restarts service.
        If no target specified, deploys to ALL online devices in the project."""
        from nso.engine.storage.zar_packer import pack
        from nso.engine.mesh.service import (
            deploy_to_device, list_devices, get_group, exec_on_device,
        )

        # Pack workspace
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path:
            return json.dumps({"error": "Workspace has no path"})

        try:
            zar_bytes, manifest = pack(
                workspace_path=ws_path,
                branch=branch,
                project_id=ctx.project_id,
            )
        except FileNotFoundError:
            return json.dumps({"error": f"Workspace directory not found: {ws_path}"})

        # Write .zar to temp file for SCP upload
        tmp = tempfile.NamedTemporaryFile(suffix=".zar", delete=False)
        tmp.write(zar_bytes)
        tmp.close()
        zar_path = tmp.name

        try:
            # Resolve target devices
            device_ids = []

            if target.startswith("grp_"):
                # Deploy to group
                try:
                    group = await get_group(ctx.project_id, target)
                    device_ids = group.get("device_ids", [])
                except Exception as e:
                    return json.dumps({"error": f"Group not found: {e}"})
            elif target.startswith("dev_"):
                # Deploy to single device
                device_ids = [target]
            else:
                # Deploy to all online devices
                devices = await list_devices(ctx.project_id, status="online")
                device_ids = [d["id"] for d in devices]

            if not device_ids:
                return json.dumps({"error": "No target devices found. Register and activate devices first."})

            # Deploy to each device concurrently
            async def _deploy_one(did: str) -> dict:
                try:
                    result = await deploy_to_device(
                        project_id=ctx.project_id,
                        device_id=did,
                        zar_path=zar_path,
                        target_dir=target_dir,
                    )
                    # Run restart command if provided
                    if restart_command and result.get("exit_code", -1) == 0:
                        restart_result = await exec_on_device(
                            project_id=ctx.project_id,
                            device_id=did,
                            command=restart_command,
                            timeout=30,
                            triggered_by="deploy_agent",
                        )
                        result["restart_exit_code"] = restart_result.get("exit_code", -1)
                        result["restart_output"] = restart_result.get("output", "")
                    return result
                except Exception as e:
                    return {"device_id": did, "error": str(e), "exit_code": -1}

            results = await asyncio.gather(*[_deploy_one(did) for did in device_ids])

            succeeded = sum(1 for r in results if r.get("exit_code", -1) == 0)
            failed = len(results) - succeeded

            return json.dumps({
                "ok": failed == 0,
                "workspace": workspace,
                "version": manifest.version,
                "branch": branch,
                "target_dir": target_dir,
                "total": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "results": [
                    {
                        "device_id": r.get("device_id", ""),
                        "exit_code": r.get("exit_code", -1),
                        "duration_ms": r.get("duration_ms", 0),
                        "error": r.get("error", ""),
                    }
                    for r in results
                ],
            })
        finally:
            import os as _os
            try:
                _os.unlink(zar_path)
            except OSError:
                pass

    async def mesh_device_status(device_id: str) -> str:
        """Get live health status and system metrics for a mesh device.
        Checks SSH connectivity, CPU load, memory, and disk usage."""
        from nso.engine.mesh.service import get_device_status

        try:
            status = await get_device_status(ctx.project_id, device_id)
        except Exception as e:
            return json.dumps({"error": str(e)})

        device = status.get("device", {})
        return json.dumps({
            "device_id": device_id,
            "name": device.get("name", ""),
            "host": device.get("host", ""),
            "status": device.get("status", "unknown"),
            "live": status.get("live", False),
            "last_seen": device.get("last_seen_at", ""),
            "metrics": status.get("raw_metrics", ""),
        })

    async def manage_mesh_group(
        action: str,
        group_name: str = "",
        group_id: str = "",
        description: str = "",
        device_ids: str = "",
    ) -> str:
        """Manage mesh groups. action: create, add_devices, remove_device, delete, status.
        device_ids: comma-separated device IDs for add_devices (e.g. 'dev_abc123,dev_def456')."""
        from nso.engine.mesh.service import (
            create_group, delete_group, add_devices_to_group,
            remove_device_from_group, group_status,
        )

        if action == "create":
            if not group_name:
                return json.dumps({"error": "group_name required for create"})
            try:
                group = await create_group(ctx.project_id, group_name, description)
            except Exception as e:
                return json.dumps({"error": str(e)})
            return json.dumps({
                "ok": True,
                "group_id": group["id"],
                "name": group_name,
                "message": f"Group '{group_name}' created. Add devices with manage_mesh_group(action='add_devices').",
            })

        if action == "add_devices":
            if not group_id:
                return json.dumps({"error": "group_id required"})
            ids = [d.strip() for d in device_ids.split(",") if d.strip()]
            if not ids:
                return json.dumps({"error": "device_ids required (comma-separated)"})
            try:
                await add_devices_to_group(ctx.project_id, group_id, ids)
            except Exception as e:
                return json.dumps({"error": str(e)})
            return json.dumps({"ok": True, "group_id": group_id, "added": ids})

        if action == "remove_device":
            if not group_id or not device_ids:
                return json.dumps({"error": "group_id and device_ids required"})
            did = device_ids.split(",")[0].strip()
            try:
                await remove_device_from_group(ctx.project_id, group_id, did)
            except Exception as e:
                return json.dumps({"error": str(e)})
            return json.dumps({"ok": True, "group_id": group_id, "removed": did})

        if action == "delete":
            if not group_id:
                return json.dumps({"error": "group_id required"})
            try:
                await delete_group(ctx.project_id, group_id)
            except Exception as e:
                return json.dumps({"error": str(e)})
            return json.dumps({"ok": True, "deleted": group_id})

        if action == "status":
            if not group_id:
                return json.dumps({"error": "group_id required"})
            try:
                status = await group_status(ctx.project_id, group_id)
            except Exception as e:
                return json.dumps({"error": str(e)})
            return json.dumps({
                "group_id": group_id,
                "name": status["group"].get("name", ""),
                "total": status["total"],
                "online": status["online"],
                "offline": status["offline"],
            })

        return json.dumps({"error": f"Unknown action '{action}'. Use: create, add_devices, remove_device, delete, status"})

    return [
        (list_mesh_devices, "list_mesh_devices",
         "List all mesh devices (external servers: Hetzner, OVH, RPi, bare metal, etc.) registered for this project"),
        (list_mesh_groups, "list_mesh_groups",
         "List mesh device groups for batch operations across multiple servers"),
        (register_mesh_device, "register_mesh_device",
         "Register a new external server to the mesh (any provider: Hetzner, OVH, DigitalOcean, bare metal, Raspberry Pi)"),
        (exec_on_mesh_device, "exec_on_mesh_device",
         "Execute a command on a single mesh device via SSH"),
        (exec_on_mesh_group, "exec_on_mesh_group",
         "Execute a command on ALL devices in a mesh group concurrently"),
        (deploy_to_mesh, "deploy_to_mesh",
         "Deploy a workspace (.zar) to mesh devices — single device, group, or all online devices"),
        (mesh_device_status, "mesh_device_status",
         "Get live health status and system metrics for a mesh device"),
        (manage_mesh_group, "manage_mesh_group",
         "Manage mesh groups: create, add/remove devices, delete, check status"),
    ]
