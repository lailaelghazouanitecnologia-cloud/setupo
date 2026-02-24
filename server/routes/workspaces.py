"""Workspace routes — create, manage, and deploy workspaces.

Workspaces live under workspaces/{name}/ with a config.toml each.
"""
import asyncio
import os
import logging
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from core import db
from core.models import (
    CreateWorkspaceRequest,
    WorkspaceConfig,
    WorkspaceGitConfig,
    WorkspaceDeployConfig,
    WorkspaceServiceConfig,
    WorkspaceType,
)
from core.workspace_config import read_config, write_config, generate_config_toml
from server.deps import require_project
from server.config import settings

logger = logging.getLogger("setupo.workspaces")
router = APIRouter()


def _ws_path(name: str) -> str:
    """Resolve workspace directory path."""
    return str(settings.workspace_path(name))


# ── CRUD ─────────────────────────────────────────────────────────

@router.post("")
async def create_workspace(req: CreateWorkspaceRequest, project_id: str = Depends(require_project)):
    """Create a workspace with config.toml — optionally clone from git."""
    existing = await db.fetch_one("workspaces", project_id=project_id, name=req.name)
    if existing:
        raise HTTPException(409, f"Workspace '{req.name}' already exists")

    ws_path = _ws_path(req.name)
    ws_id = f"ws_{secrets.token_hex(8)}"

    # Determine type
    ws_type = req.ws_type
    if req.git_url and ws_type == WorkspaceType.CUSTOM:
        ws_type = WorkspaceType.GIT

    # Clone or create directory
    if req.git_url:
        git_url = req.git_url
        if not git_url.startswith("http"):
            git_url = f"https://github.com/{req.git_url}.git"

        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", "-b", req.branch, git_url, ws_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            raise HTTPException(500, f"Clone failed: {stdout.decode()}")
    else:
        os.makedirs(ws_path, exist_ok=True)

    # Generate config.toml
    config = WorkspaceConfig(
        name=req.name,
        type=req.stack or "custom",
        description=req.description,
        git=WorkspaceGitConfig(
            url=req.git_url,
            branch=req.branch,
        ),
        deploy=WorkspaceDeployConfig(
            instance_id=req.instance_id,
        ),
        services={"nginx": WorkspaceServiceConfig()} if req.stack != "custom" else {},
    )
    write_config(ws_path, config)

    # Save to DB
    now = datetime.utcnow().isoformat()
    await db.insert("workspaces", {
        "id": ws_id,
        "project_id": project_id,
        "name": req.name,
        "path": ws_path,
        "ws_type": ws_type.value,
        "stack": req.stack,
        "description": req.description,
        "instance_id": req.instance_id,
        "git_url": req.git_url,
        "branch": req.branch,
        "created_at": now,
        "updated_at": now,
    })

    logger.info("Created workspace '%s' [%s] for project %s", req.name, ws_type.value, project_id)
    ws_record = await db.fetch_one("workspaces", id=ws_id)
    return {"workspace": ws_record, "config": config.model_dump()}


@router.get("")
async def list_workspaces(project_id: str = Depends(require_project)):
    """List all workspaces with their config.toml info."""
    workspaces = await db.fetch_all("workspaces", project_id=project_id)

    for ws in workspaces:
        ws_path = ws.get("path", "")
        # Read config.toml
        config = read_config(ws_path)
        ws["config"] = config.model_dump() if config else None
        # Git info
        git_dir = os.path.join(ws_path, ".git")
        ws["is_git"] = os.path.isdir(git_dir)
        ws["exists"] = os.path.isdir(ws_path)

    return {"workspaces": workspaces}


@router.get("/{name}")
async def get_workspace(name: str, project_id: str = Depends(require_project)):
    """Get workspace details including config.toml."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    config = read_config(ws_path)
    ws["config"] = config.model_dump() if config else None
    ws["exists"] = os.path.isdir(ws_path)

    return {"workspace": ws}


@router.delete("/{name}")
async def delete_workspace(name: str, project_id: str = Depends(require_project)):
    """Delete a workspace and its directory."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if os.path.isdir(ws_path):
        shutil.rmtree(ws_path, ignore_errors=True)

    await db.delete("workspaces", ws["id"])
    logger.info("Deleted workspace '%s'", name)
    return {"deleted": name}


# ── Config ───────────────────────────────────────────────────────

class UpdateConfigRequest(BaseModel):
    type: str | None = None
    description: str | None = None
    instance_id: str | None = None
    command: str | None = None
    port: int | None = None
    env: dict[str, str] | None = None


@router.get("/{name}/config")
async def get_config(name: str, project_id: str = Depends(require_project)):
    """Read the config.toml for a workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    config = read_config(ws["path"])
    if not config:
        raise HTTPException(404, "config.toml not found in workspace")

    # Also return raw TOML
    raw = generate_config_toml(config)
    return {"config": config.model_dump(), "raw": raw}


@router.put("/{name}/config")
async def update_config(name: str, req: UpdateConfigRequest, project_id: str = Depends(require_project)):
    """Update the config.toml for a workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    config = read_config(ws["path"])
    if not config:
        config = WorkspaceConfig(name=name)

    # Merge updates
    if req.type is not None:
        config.type = req.type
    if req.description is not None:
        config.description = req.description
    if req.instance_id is not None:
        config.deploy.instance_id = req.instance_id
    if req.command is not None:
        config.deploy.command = req.command
    if req.port is not None:
        config.deploy.port = req.port
    if req.env is not None:
        config.deploy.env.update(req.env)

    write_config(ws["path"], config)

    # Update DB fields too
    updates = {"updated_at": datetime.utcnow().isoformat()}
    if req.type is not None:
        updates["stack"] = req.type
    if req.description is not None:
        updates["description"] = req.description
    if req.instance_id is not None:
        updates["instance_id"] = req.instance_id
    await db.update("workspaces", ws["id"], updates)

    return {"config": config.model_dump(), "raw": generate_config_toml(config)}


# ── Git operations ───────────────────────────────────────────────

@router.post("/{name}/pull")
async def pull_workspace(name: str, project_id: str = Depends(require_project)):
    """Git pull in workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if not os.path.isdir(os.path.join(ws_path, ".git")):
        raise HTTPException(400, "Workspace is not a git repository")

    proc = await asyncio.create_subprocess_exec(
        "git", "-C", ws_path, "pull", "--ff-only",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return {"name": name, "output": stdout.decode().strip(), "success": proc.returncode == 0}


# ── File operations ──────────────────────────────────────────────

@router.get("/{name}/files")
async def list_files(name: str, path: str = Query("."), project_id: str = Depends(require_project)):
    """List files in a workspace directory."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    full_path = os.path.normpath(os.path.join(ws["path"], path))
    if not full_path.startswith(ws["path"]):
        raise HTTPException(403, "Path traversal denied")

    if not os.path.isdir(full_path):
        raise HTTPException(404, "Directory not found")

    items = []
    for entry in sorted(os.scandir(full_path), key=lambda e: (not e.is_dir(), e.name)):
        if entry.name.startswith("."):
            continue
        stat = entry.stat()
        items.append({
            "name": entry.name,
            "path": os.path.relpath(entry.path, ws["path"]),
            "type": "dir" if entry.is_dir() else "file",
            "size": stat.st_size if entry.is_file() else 0,
            "modified": stat.st_mtime,
        })

    return {"path": path, "items": items}


@router.get("/{name}/files/read")
async def read_file(name: str, path: str = Query(...), project_id: str = Depends(require_project)):
    """Read a file from the workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    full_path = os.path.normpath(os.path.join(ws["path"], path))
    if not full_path.startswith(ws["path"]):
        raise HTTPException(403, "Path traversal denied")

    if not os.path.isfile(full_path):
        raise HTTPException(404, "File not found")

    size = os.path.getsize(full_path)
    if size > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5MB)")

    with open(full_path, "r", errors="replace") as f:
        content = f.read()

    return {"path": path, "content": content, "size": size}


class WriteFileRequest(BaseModel):
    path: str
    content: str


@router.post("/{name}/files/write")
async def write_file(name: str, req: WriteFileRequest, project_id: str = Depends(require_project)):
    """Write/create a file in the workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    full_path = os.path.normpath(os.path.join(ws["path"], req.path))
    if not full_path.startswith(ws["path"]):
        raise HTTPException(403, "Path traversal denied")

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(req.content)

    # Update workspace timestamp
    await db.update("workspaces", ws["id"], {"updated_at": datetime.utcnow().isoformat()})

    return {"path": req.path, "written": True, "size": len(req.content)}


class DeleteFileRequest(BaseModel):
    path: str


@router.post("/{name}/files/delete")
async def delete_file(name: str, req: DeleteFileRequest, project_id: str = Depends(require_project)):
    """Delete a file from the workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    full_path = os.path.normpath(os.path.join(ws["path"], req.path))
    if not full_path.startswith(ws["path"]):
        raise HTTPException(403, "Path traversal denied")

    if not os.path.exists(full_path):
        raise HTTPException(404, "File not found")

    if os.path.isdir(full_path):
        shutil.rmtree(full_path)
    else:
        os.remove(full_path)

    return {"path": req.path, "deleted": True}


# ── Deploy shortcut ──────────────────────────────────────────────

@router.post("/{name}/deploy")
async def deploy_workspace(name: str, project_id: str = Depends(require_project)):
    """Deploy a workspace using its config.toml settings.

    Reads instance_id and command from config.toml, then triggers deploy.
    """
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    config = read_config(ws["path"])
    if not config:
        raise HTTPException(400, "No config.toml found — cannot determine deploy target")

    instance_id = config.deploy.instance_id or ws.get("instance_id")
    if not instance_id:
        raise HTTPException(400, "No instance_id in config.toml — link a workspace to an instance first")

    from core.deploy.pipeline import deploy_to_instance
    result = await deploy_to_instance(
        project_id=project_id,
        instance_id=instance_id,
        workspace_name=name,
        command=config.deploy.command,
    )
    return result
