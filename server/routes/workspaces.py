"""Workspace routes — project-scoped file/git workspace management."""
import asyncio
import os
import logging
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from core import db
from core.models import CreateWorkspaceRequest
from core.errors import NotFoundError, ConflictError
from server.deps import require_project
from server.config import settings

logger = logging.getLogger("setupo.workspaces")
router = APIRouter()


@router.post("")
async def create_workspace(req: CreateWorkspaceRequest, project_id: str = Depends(require_project)):
    """Create a workspace — optionally clone from a git repo."""
    existing = await db.fetch_one("workspaces", project_id=project_id, name=req.name)
    if existing:
        raise HTTPException(409, f"Workspace '{req.name}' already exists")

    ws_path = str(settings.workspace_dir(project_id, req.name))
    ws_id = f"ws_{secrets.token_hex(8)}"

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

    await db.insert("workspaces", {
        "id": ws_id,
        "project_id": project_id,
        "name": req.name,
        "path": ws_path,
        "git_url": req.git_url,
        "branch": req.branch,
    })

    logger.info("Created workspace %s for project %s", req.name, project_id)
    return {
        "workspace": {
            "id": ws_id,
            "name": req.name,
            "path": ws_path,
            "git_url": req.git_url,
            "branch": req.branch,
        }
    }


@router.get("")
async def list_workspaces(project_id: str = Depends(require_project)):
    """List all workspaces in this project."""
    workspaces = await db.fetch_all("workspaces", project_id=project_id)
    # Enrich with git info
    for ws in workspaces:
        ws_path = ws.get("path", "")
        git_dir = os.path.join(ws_path, ".git")
        ws["is_git"] = os.path.isdir(git_dir)
        if ws["is_git"]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "-C", ws_path, "branch", "--show-current",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                ws["current_branch"] = stdout.decode().strip()
            except Exception:
                pass
    return {"workspaces": workspaces}


@router.get("/{name}")
async def get_workspace(name: str, project_id: str = Depends(require_project)):
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")
    return {"workspace": ws}


@router.delete("/{name}")
async def delete_workspace(name: str, project_id: str = Depends(require_project)):
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if os.path.isdir(ws_path):
        shutil.rmtree(ws_path, ignore_errors=True)

    await db.delete("workspaces", ws["id"])
    logger.info("Deleted workspace %s", name)
    return {"deleted": name}


@router.post("/{name}/pull")
async def pull_workspace(name: str, project_id: str = Depends(require_project)):
    """Git pull in workspace."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", ws_path, "pull", "--ff-only",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return {"name": name, "output": stdout.decode().strip(), "success": proc.returncode == 0}


# ── File operations within workspace ──────────────────────────

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

    return {"path": req.path, "written": True, "size": len(req.content)}
