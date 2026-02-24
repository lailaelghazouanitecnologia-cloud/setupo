"""Capsule (plugin/module) management routes."""
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from pydantic import BaseModel
import json

router = APIRouter()


class LoadCapsuleRequest(BaseModel):
    capsule_name: str
    target_instance: str
    config: dict = {}


@router.get("/")
async def list_capsules(request: Request):
    """List available capsules."""
    orch = request.app.state.orchestrator
    loader = _get_loader()
    available = loader.list_capsules() if loader else []
    return {"capsules": available}


@router.post("/load")
async def load_capsule(req: LoadCapsuleRequest, request: Request):
    """Load a capsule into a VM/MicroVM."""
    orch = request.app.state.orchestrator
    instance = orch.instances.get(req.target_instance)
    if not instance:
        raise HTTPException(404, f"Instance {req.target_instance} not found")

    # Execute capsule's install script on the target instance
    result = await orch.exec_on_instance(
        req.target_instance,
        f"cd /opt/capsules && ./install.sh {req.capsule_name}"
    )
    instance.capsules.append(req.capsule_name)
    return {"status": "loaded", "capsule": req.capsule_name, "result": result}


@router.post("/upload")
async def upload_capsule(file: UploadFile = File(...)):
    """Upload a new capsule package."""
    import aiofiles
    from pathlib import Path

    capsule_dir = Path("/var/lib/setupo/capsules")
    capsule_dir.mkdir(parents=True, exist_ok=True)
    dest = capsule_dir / file.filename

    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    return {"status": "uploaded", "filename": file.filename, "size": len(content)}


@router.delete("/{capsule_name}")
async def delete_capsule(capsule_name: str):
    """Remove a capsule."""
    from pathlib import Path
    path = Path("/var/lib/setupo/capsules") / capsule_name
    if not path.exists():
        raise HTTPException(404, f"Capsule {capsule_name} not found")
    import shutil
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return {"status": "deleted", "capsule": capsule_name}


def _get_loader():
    try:
        from capsules.loader import CapsuleLoader
        return CapsuleLoader()
    except ImportError:
        return None
