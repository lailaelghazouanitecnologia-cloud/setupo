"""Capsule CRUD routes."""
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File

from core.models import CreateCapsuleRequest
from server.auth import require_token

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/")
async def list_capsules(request: Request, state: str = None):
    engine = request.app.state.engine
    capsules = await engine.store.list_capsules(state=state)
    return {"capsules": capsules, "count": len(capsules)}


@router.post("/")
async def create_capsule(req: CreateCapsuleRequest, request: Request):
    engine = request.app.state.engine
    capsule = await engine.create_capsule(req)
    return {"capsule": capsule}


@router.get("/{capsule_id}")
async def get_capsule(capsule_id: str, request: Request):
    engine = request.app.state.engine
    capsule = await engine.store.get_capsule(capsule_id)
    if not capsule:
        raise HTTPException(404, f"Capsule {capsule_id} not found")
    return {"capsule": capsule}


@router.post("/{capsule_id}/build")
async def build_capsule(capsule_id: str, request: Request):
    engine = request.app.state.engine
    try:
        capsule = await engine.build_capsule(capsule_id)
        return {"capsule": capsule}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{capsule_id}/start")
async def start_capsule(capsule_id: str, request: Request):
    engine = request.app.state.engine
    try:
        capsule = await engine.start_capsule(capsule_id)
        return {"capsule": capsule}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{capsule_id}/stop")
async def stop_capsule(capsule_id: str, request: Request):
    engine = request.app.state.engine
    try:
        capsule = await engine.stop_capsule(capsule_id)
        return {"capsule": capsule}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{capsule_id}")
async def destroy_capsule(capsule_id: str, request: Request):
    engine = request.app.state.engine
    try:
        return await engine.destroy_capsule(capsule_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{capsule_id}/logs")
async def capsule_logs(capsule_id: str, request: Request):
    engine = request.app.state.engine
    try:
        logs = await engine.get_capsule_logs(capsule_id)
        return {"logs": logs}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{capsule_id}/call")
async def call_capsule(capsule_id: str, request: Request):
    """Make an HTTP call to a capsule's service."""
    engine = request.app.state.engine
    body = await request.json()
    path = body.get("path", "/")
    method = body.get("method", "GET")
    data = body.get("body")
    try:
        return await engine.call_capsule(capsule_id, path, method, data)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{capsule_id}/upload")
async def upload_file(capsule_id: str, file: UploadFile = File(...), request: Request = None):
    """Upload a file to a capsule's workspace."""
    engine = request.app.state.engine
    capsule = await engine.store.get_capsule(capsule_id)
    if not capsule:
        raise HTTPException(404, f"Capsule {capsule_id} not found")
    content = await file.read()
    path = engine.sandbox.write_capsule_code(capsule_id, file.filename, content.decode())
    return {"status": "uploaded", "path": str(path), "size": len(content)}
