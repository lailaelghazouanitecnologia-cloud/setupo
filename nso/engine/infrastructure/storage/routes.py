import logging

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import Response
from pydantic import BaseModel

from nso.shared.deps import require_project
from nso.shared.errors import NsoError
from nso.engine.infrastructure.storage import service

logger = logging.getLogger("nso.infrastructure.storage")
router = APIRouter()


class CreateBucketRequest(BaseModel):
    name: str
    public_access: bool = False


# ── Bucket CRUD ──────────────────────────────────────────────────

@router.post("/buckets")
async def create_bucket(req: CreateBucketRequest, project_id: str = Depends(require_project)):
    try:
        return await service.create_bucket(project_id, req.name, req.public_access)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/buckets")
async def list_buckets(project_id: str = Depends(require_project)):
    buckets = await service.list_buckets(project_id)
    return {"buckets": buckets, "count": len(buckets)}


@router.get("/buckets/{bucket_id}")
async def get_bucket(bucket_id: str, project_id: str = Depends(require_project)):
    try:
        return await service.get_bucket(project_id, bucket_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/buckets/{bucket_id}")
async def delete_bucket(bucket_id: str, project_id: str = Depends(require_project)):
    try:
        await service.delete_bucket(project_id, bucket_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ── Object operations ────────────────────────────────────────────

@router.get("/buckets/{bucket_id}/objects")
async def list_objects(bucket_id: str, prefix: str = "",
                       project_id: str = Depends(require_project)):
    try:
        objects = await service.list_objects(project_id, bucket_id, prefix)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"objects": objects, "count": len(objects)}


@router.post("/buckets/{bucket_id}/upload")
async def upload_object(bucket_id: str, file: UploadFile = File(...),
                        key: str = Query(None),
                        project_id: str = Depends(require_project)):
    object_key = key or file.filename or "unnamed"
    data = await file.read()

    # 100MB limit
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 100MB)")

    try:
        result = await service.upload_object(
            project_id, bucket_id, object_key, data,
            content_type=file.content_type or "application/octet-stream",
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.get("/buckets/{bucket_id}/download/{key:path}")
async def download_object(bucket_id: str, key: str,
                          project_id: str = Depends(require_project)):
    try:
        data = await service.download_object(project_id, bucket_id, key)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    if data is None:
        raise HTTPException(404, "Object not found")

    # Guess content type from extension
    content_type = "application/octet-stream"
    if key.endswith(".json"):
        content_type = "application/json"
    elif key.endswith(".html"):
        content_type = "text/html"
    elif key.endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif key.endswith(".png"):
        content_type = "image/png"
    elif key.endswith(".txt"):
        content_type = "text/plain"
    elif key.endswith(".css"):
        content_type = "text/css"
    elif key.endswith(".js"):
        content_type = "application/javascript"

    return Response(content=data, media_type=content_type)


@router.delete("/buckets/{bucket_id}/objects/{key:path}")
async def delete_object(bucket_id: str, key: str,
                        project_id: str = Depends(require_project)):
    try:
        await service.delete_object(project_id, bucket_id, key)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}
