"""MMS File System - Browse and edit files on the server."""
import os
import stat
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.auth import require_token

logger = logging.getLogger("mms.fs")
router = APIRouter()

# Allowed base paths (security)
ALLOWED_ROOTS = ["/opt/mms", "/var/www/mms", "/var/log", "/etc/mms", "/tmp/mms"]


def _validate_path(path: str) -> Path:
    """Ensure path is within allowed roots."""
    p = Path(path).resolve()
    if not any(str(p).startswith(root) for root in ALLOWED_ROOTS):
        raise HTTPException(403, f"Access denied: {path}")
    return p


class WriteFileRequest(BaseModel):
    path: str
    content: str


class MkdirRequest(BaseModel):
    path: str


@router.get("/list")
async def list_dir(path: str = "/opt/mms", _=Depends(require_token)):
    """List directory contents."""
    p = _validate_path(path)
    if not p.is_dir():
        raise HTTPException(404, "Not a directory")

    items = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                st = entry.stat()
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "dir" if entry.is_dir() else "file",
                    "size": st.st_size if entry.is_file() else None,
                    "modified": st.st_mtime,
                    "permissions": stat.filemode(st.st_mode),
                })
            except PermissionError:
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "unknown",
                    "size": None,
                    "modified": None,
                    "permissions": "----------",
                })
    except PermissionError:
        raise HTTPException(403, "Permission denied")

    return {"path": str(p), "items": items, "count": len(items)}


@router.get("/read")
async def read_file(path: str, _=Depends(require_token)):
    """Read file contents."""
    p = _validate_path(path)
    if not p.is_file():
        raise HTTPException(404, "Not a file")
    if p.stat().st_size > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(413, "File too large (max 5MB)")

    try:
        content = p.read_text(errors="replace")
    except Exception as e:
        raise HTTPException(500, f"Error reading file: {e}")

    return {"path": str(p), "content": content, "size": p.stat().st_size}


@router.post("/write")
async def write_file(req: WriteFileRequest, _=Depends(require_token)):
    """Write/create file."""
    p = _validate_path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)

    try:
        p.write_text(req.content)
    except Exception as e:
        raise HTTPException(500, f"Error writing file: {e}")

    return {"path": str(p), "size": p.stat().st_size}


@router.post("/mkdir")
async def mkdir(req: MkdirRequest, _=Depends(require_token)):
    """Create directory."""
    p = _validate_path(req.path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(500, f"Error creating directory: {e}")
    return {"path": str(p)}


@router.delete("/delete")
async def delete_path(path: str, _=Depends(require_token)):
    """Delete file or empty directory."""
    p = _validate_path(path)
    if not p.exists():
        raise HTTPException(404, "Path not found")

    try:
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        else:
            p.unlink()
    except Exception as e:
        raise HTTPException(500, f"Error deleting: {e}")

    return {"deleted": str(p)}
