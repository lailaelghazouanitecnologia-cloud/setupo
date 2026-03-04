import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import require_admin, AdminUser

logger = logging.getLogger("z86-agent.files")
router = APIRouter(prefix="/files", tags=["files"])

# z86 agent can access z86 code, data, and logs
ALLOWED_ROOTS = ["/opt/nso", "/data/z86", "/var/log", "/tmp"]
MAX_READ_SIZE = 5 * 1024 * 1024
DEFAULT_PATH = "/opt/nso/z86"
SKIP_DIRS = frozenset({"node_modules", "__pycache__", ".git", "venv", ".venv"})


def _safe_path(path: str) -> Path:
    if not path:
        path = DEFAULT_PATH
    resolved = Path(path).resolve()
    for root in ALLOWED_ROOTS:
        if str(resolved).startswith(root):
            return resolved
    raise HTTPException(403, "Access denied: path outside allowed directories")


class FSItem(BaseModel):
    name: str
    path: str
    type: str
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


@router.get("/list", response_model=DirListing)
async def list_directory(
    path: str = Query(DEFAULT_PATH),
    admin: AdminUser = Depends(require_admin),
):
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
    path: str = Query(...),
    admin: AdminUser = Depends(require_admin),
):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(404, f"File not found: {path}")
    if not target.is_file():
        raise HTTPException(400, f"Not a file: {path}")
    size = target.stat().st_size
    if size > MAX_READ_SIZE:
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
    target = _safe_path(req.path)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {req.path}")
    logger.info("Created directory: %s", target)
    return {"ok": True, "path": str(target)}


@router.delete("/")
async def delete_path(
    path: str = Query(...),
    admin: AdminUser = Depends(require_admin),
):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(404, f"Path not found: {path}")
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
    path: str = Query(DEFAULT_PATH),
    depth: int = Query(3, ge=1, le=5),
    admin: AdminUser = Depends(require_admin),
):
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
                    if child.name in SKIP_DIRS:
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
