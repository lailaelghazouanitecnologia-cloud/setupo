"""MMS Workspaces - GitHub repo cloning and management."""
import asyncio
import os
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.auth import require_token

logger = logging.getLogger("mms.workspaces")
router = APIRouter()

WORKSPACE_ROOT = "/opt/mms/workspaces"


class CloneRequest(BaseModel):
    repo: str  # e.g. "user/repo" or full URL
    branch: str = "main"
    name: str | None = None  # auto from repo name if None


@router.get("/")
async def list_workspaces(_=Depends(require_token)):
    """List all workspaces."""
    if not os.path.isdir(WORKSPACE_ROOT):
        return {"workspaces": [], "count": 0}

    workspaces = []
    for entry in sorted(os.scandir(WORKSPACE_ROOT), key=lambda e: e.name):
        if entry.is_dir():
            git_dir = os.path.join(entry.path, ".git")
            is_git = os.path.isdir(git_dir)
            ws = {
                "name": entry.name,
                "path": entry.path,
                "is_git": is_git,
                "modified": entry.stat().st_mtime,
            }
            # Get git info
            if is_git:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "git", "-C", entry.path, "remote", "get-url", "origin",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, _ = await proc.communicate()
                    ws["repo"] = stdout.decode().strip()

                    proc2 = await asyncio.create_subprocess_exec(
                        "git", "-C", entry.path, "branch", "--show-current",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    stdout2, _ = await proc2.communicate()
                    ws["branch"] = stdout2.decode().strip()
                except Exception:
                    pass
            workspaces.append(ws)

    return {"workspaces": workspaces, "count": len(workspaces)}


@router.post("/clone")
async def clone_repo(req: CloneRequest, _=Depends(require_token)):
    """Clone a GitHub repo as workspace."""
    repo_url = req.repo
    if not repo_url.startswith("http"):
        repo_url = f"https://github.com/{req.repo}.git"

    name = req.name or req.repo.split("/")[-1].replace(".git", "")
    dest = os.path.join(WORKSPACE_ROOT, name)

    if os.path.exists(dest):
        raise HTTPException(409, f"Workspace '{name}' already exists")

    os.makedirs(WORKSPACE_ROOT, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", "-b", req.branch, repo_url, dest,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()

    if proc.returncode != 0:
        raise HTTPException(500, f"Clone failed: {stdout.decode()}")

    logger.info("Cloned %s → %s", repo_url, dest)
    return {"name": name, "path": dest, "repo": repo_url, "branch": req.branch}


@router.post("/{name}/pull")
async def pull_workspace(name: str, _=Depends(require_token)):
    """Git pull in workspace."""
    ws_path = os.path.join(WORKSPACE_ROOT, name)
    if not os.path.isdir(ws_path):
        raise HTTPException(404, f"Workspace '{name}' not found")

    proc = await asyncio.create_subprocess_exec(
        "git", "-C", ws_path, "pull", "--ff-only",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode().strip()

    return {"name": name, "output": output, "success": proc.returncode == 0}


@router.delete("/{name}")
async def delete_workspace(name: str, _=Depends(require_token)):
    """Delete a workspace."""
    ws_path = os.path.join(WORKSPACE_ROOT, name)
    if not os.path.isdir(ws_path):
        raise HTTPException(404, f"Workspace '{name}' not found")

    import shutil
    shutil.rmtree(ws_path)
    logger.info("Deleted workspace '%s'", name)
    return {"deleted": name}
