"""MMS Agent — File system operations.

Browse directories, read/write files, create dirs, delete — all via HTTP.
No SSH needed. The agent on the VPS handles it.
"""
import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("mms-agent.files")
router = APIRouter(prefix="/files", tags=["files"])

# Allowed root paths — prevent escaping
ALLOWED_ROOTS = ["/opt/setupo", "/opt/app", "/var/log/setupo", "/tmp"]


def _safe_path(path: str) -> Path:
    """Resolve and validate a path is within allowed roots."""
    if not path:
        path = "/opt/setupo"
    resolved = Path(path).resolve()
    for root in ALLOWED_ROOTS:
        if str(resolved).startswith(root):
            return resolved
    raise HTTPException(403, f"Access denied: path outside allowed directories")


# ── Models ───────────────────────────────────────────────────────

class FSItem(BaseModel):
    name: str
    path: str
    type: str  # "file" | "dir" | "link" | "unknown"
    size: Optional[int] = None
    modified: Optional[float] = None
    permissions: str = ""


class DirListing(BaseModel):
    path: str
    items: list[FSItem]
    count: int


class FileContent(BaseModel):
    path: str
    content: str
    size: int


class WriteRequest(BaseModel):
    path: str
    content: str


class MkdirRequest(BaseModel):
    path: str


# ── Helpers ──────────────────────────────────────────────────────

def _stat_item(p: Path) -> FSItem:
    try:
        st = p.stat()
        if p.is_symlink():
            ftype = "link"
        elif p.is_dir():
            ftype = "dir"
        elif p.is_file():
            ftype = "file"
        else:
            ftype = "unknown"
        return FSItem(
            name=p.name,
            path=str(p),
            type=ftype,
            size=st.st_size if ftype == "file" else None,
            modified=st.st_mtime,
            permissions=stat.filemode(st.st_mode),
        )
    except PermissionError:
        return FSItem(name=p.name, path=str(p), type="unknown", permissions="?????????")
    except Exception:
        return FSItem(name=p.name, path=str(p), type="unknown")


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/list", response_model=DirListing)
async def list_directory(
    path: str = Query("/opt/setupo", description="Directory to list"),
    admin: AdminUser = Depends(require_admin),
):
    """List contents of a directory.

    curl -H "Authorization: Bearer <token>" \\
      "https://server:8081/files/list?path=/opt/setupo"
    """
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(404, f"Path not found: {path}")
    if not target.is_dir():
        raise HTTPException(400, f"Not a directory: {path}")

    items = []
    try:
        for child in sorted(target.iterdir()):
            items.append(_stat_item(child))
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {path}")

    return DirListing(path=str(target), items=items, count=len(items))


@router.get("/read", response_model=FileContent)
async def read_file(
    path: str = Query(..., description="File path to read"),
    admin: AdminUser = Depends(require_admin),
):
    """Read contents of a file.

    curl -H "Authorization: Bearer <token>" \\
      "https://server:8081/files/read?path=/opt/setupo/.env"
    """
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(404, f"File not found: {path}")
    if not target.is_file():
        raise HTTPException(400, f"Not a file: {path}")

    # Limit file size to 5MB
    size = target.stat().st_size
    if size > 5 * 1024 * 1024:
        raise HTTPException(413, f"File too large: {size} bytes (max 5MB)")

    try:
        content = target.read_text(errors="replace")
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {path}")

    return FileContent(path=str(target), content=content, size=size)


@router.post("/write")
async def write_file(
    req: WriteRequest,
    admin: AdminUser = Depends(require_admin),
):
    """Write content to a file (creates or overwrites).

    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"path":"/opt/app/index.html","content":"<h1>Hello</h1>"}' \\
      https://server:8081/files/write
    """
    target = _safe_path(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.write_text(req.content)
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {req.path}")

    logger.info("Wrote file: %s (%d bytes)", target, len(req.content))
    return {"ok": True, "path": str(target), "size": len(req.content)}


@router.post("/mkdir")
async def make_directory(
    req: MkdirRequest,
    admin: AdminUser = Depends(require_admin),
):
    """Create a directory (and parents).

    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"path":"/opt/app/src"}' \\
      https://server:8081/files/mkdir
    """
    target = _safe_path(req.path)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {req.path}")

    logger.info("Created directory: %s", target)
    return {"ok": True, "path": str(target)}


@router.delete("/")
async def delete_path(
    path: str = Query(..., description="Path to delete"),
    admin: AdminUser = Depends(require_admin),
):
    """Delete a file or directory.

    curl -X DELETE -H "Authorization: Bearer <token>" \\
      "https://server:8081/files/?path=/opt/app/old-file.txt"
    """
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(404, f"Path not found: {path}")

    # Safety: never delete the root allowed dirs themselves
    for root in ALLOWED_ROOTS:
        if str(target) == root:
            raise HTTPException(403, f"Cannot delete root directory: {path}")

    try:
        if target.is_dir():
            shutil.rmtree(target)
            logger.info("Deleted directory: %s", target)
        else:
            target.unlink()
            logger.info("Deleted file: %s", target)
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {path}")

    return {"ok": True, "deleted": str(target)}


@router.get("/tree")
async def file_tree(
    path: str = Query("/opt/setupo", description="Root directory"),
    depth: int = Query(3, ge=1, le=5, description="Max depth"),
    admin: AdminUser = Depends(require_admin),
):
    """Get a directory tree (useful for agents to understand structure).

    curl -H "Authorization: Bearer <token>" \\
      "https://server:8081/files/tree?path=/opt/setupo&depth=2"
    """
    target = _safe_path(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, f"Directory not found: {path}")

    def _walk(p: Path, current_depth: int) -> dict:
        node = {"name": p.name, "path": str(p), "type": "dir", "children": []}
        if current_depth >= depth:
            return node
        try:
            for child in sorted(p.iterdir()):
                if child.name.startswith(".") and child.name not in (".env",):
                    continue
                if child.is_dir():
                    if child.name in ("node_modules", "__pycache__", ".git", "venv", ".venv"):
                        node["children"].append({"name": child.name, "path": str(child), "type": "dir", "children": "..."})
                    else:
                        node["children"].append(_walk(child, current_depth + 1))
                else:
                    node["children"].append({
                        "name": child.name,
                        "path": str(child),
                        "type": "file",
                        "size": child.stat().st_size,
                    })
        except PermissionError:
            pass
        return node

    return _walk(target, 0)
