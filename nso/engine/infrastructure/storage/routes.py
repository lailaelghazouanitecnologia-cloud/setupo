import logging

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from nso.shared.deps import require_project
from nso.shared.errors import NsoError
from nso.engine.infrastructure.storage import service

logger = logging.getLogger("nso.infrastructure.storage")
router = APIRouter()

# ── Upload safety limits ────────────────────────────────────────
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# Blocked extensions — disk images, executables, archives that hide executables
BLOCKED_EXTENSIONS = frozenset({
    # OS / disk images
    ".iso", ".img", ".vmdk", ".vhd", ".vhdx", ".qcow2", ".ova", ".ovf",
    ".dmg", ".sparseimage", ".raw",
    # Executables & installers
    ".exe", ".msi", ".dll", ".sys", ".com", ".bat", ".cmd", ".scr", ".pif",
    ".app", ".deb", ".rpm", ".AppImage", ".snap", ".flatpak",
    # Dangerous script / macro containers
    ".hta", ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".psm1",
    # Large archives often used to smuggle the above
    ".cab", ".wim", ".swm",
})

ALLOWED_CONTENT_TYPES = {
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "image/bmp", "image/tiff", "image/avif",
    # Documents
    "application/pdf", "application/json", "text/plain", "text/html",
    "text/css", "text/csv", "text/xml", "application/xml",
    # Web assets
    "application/javascript", "text/javascript",
    "application/wasm", "font/woff", "font/woff2",
    # Data
    "application/zip", "application/gzip", "application/x-tar",
    "application/x-7z-compressed",
    # Audio / video (reasonable sizes for app assets)
    "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm",
    "video/mp4", "video/webm", "video/ogg",
    # Fallback
    "application/octet-stream",
}


def _check_file_allowed(filename: str, content_type: str | None) -> None:
    """Raise HTTPException if file extension is blocked."""
    if not filename:
        return
    lower = filename.lower()
    for ext in BLOCKED_EXTENSIONS:
        if lower.endswith(ext):
            raise HTTPException(
                415,
                f"File type '{ext}' is not allowed. "
                "Disk images, executables, and installers cannot be uploaded."
            )
    # Warn on unknown MIME but don't block (application/octet-stream is catch-all)
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        logger.info("Upload with uncommon content-type: %s (%s)", content_type, filename)


class CreateBucketRequest(BaseModel):
    name: str
    public_access: bool = False


# ── Bucket CRUD ──────────────────────────────────────────────────

@router.post("/buckets", status_code=201, summary="Create bucket")
async def create_bucket(req: CreateBucketRequest, project_id: str = Depends(require_project)):
    try:
        return await service.create_bucket(project_id, req.name, req.public_access)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/buckets", summary="List buckets")
async def list_buckets(project_id: str = Depends(require_project)):
    buckets = await service.list_buckets(project_id)
    return {"buckets": buckets, "count": len(buckets)}


@router.get("/buckets/{bucket_id}", summary="Get bucket")
async def get_bucket(bucket_id: str, project_id: str = Depends(require_project)):
    try:
        return await service.get_bucket(project_id, bucket_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/buckets/{bucket_id}", summary="Delete bucket")
async def delete_bucket(bucket_id: str, project_id: str = Depends(require_project)):
    try:
        await service.delete_bucket(project_id, bucket_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ── Object operations ────────────────────────────────────────────

@router.get("/buckets/{bucket_id}/objects", summary="List objects")
async def list_objects(bucket_id: str, prefix: str = "",
                       project_id: str = Depends(require_project)):
    try:
        objects = await service.list_objects(project_id, bucket_id, prefix)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"objects": objects, "count": len(objects)}


@router.post("/buckets/{bucket_id}/upload", summary="Upload object")
async def upload_object(bucket_id: str, request: Request,
                        file: UploadFile = File(...),
                        key: str = Query(None),
                        project_id: str = Depends(require_project)):
    # ── 1. Reject blocked file types BEFORE reading any bytes ───
    filename = file.filename or key or "unnamed"
    _check_file_allowed(filename, file.content_type)

    # ── 2. Early size rejection via Content-Length header ────────
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB). "
            "Reduce file size or use a different storage solution for large files."
        )

    # ── 3. Enforce frozen check + storage limit ─────────────────
    try:
        from nso.engine.billing.service import check_project_not_frozen, _get_owner_for_project, get_user_plan_features
        await check_project_not_frozen(project_id)

        owner_id = await _get_owner_for_project(project_id)
        if owner_id:
            features = await get_user_plan_features(owner_id)
            storage_limit_gb = features.get("storage_gb", -1)
            if storage_limit_gb != -1:
                buckets = await db.fetch_all("storage_buckets", project_id=project_id)
                total_bytes = sum(b.get("size_bytes", 0) for b in buckets)
                total_gb = total_bytes / (1024 ** 3)
                if total_gb >= storage_limit_gb:
                    sub = await db.fetch_one("billing_subscriptions", user_id=owner_id, status="active")
                    is_free = not sub or sub.get("amount_cents", 0) == 0
                    if is_free:
                        raise HTTPException(
                            403,
                            f"Storage limit reached ({total_gb:.1f}GB/{storage_limit_gb}GB). "
                            f"Upgrade your plan to upload more."
                        )
                    else:
                        logger.info("Project %s over storage limit (%.1fGB/%dGB) — overage billed",
                                    project_id, total_gb, storage_limit_gb)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Storage limit check failed (allowing): %s", e)

    # ── 4. Stream-read with hard cap (never buffer more than MAX) ─
    object_key = key or filename
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(256 * 1024)  # 256 KB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB). "
                "Upload was stopped to protect server memory."
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    try:
        result = await service.upload_object(
            project_id, bucket_id, object_key, data,
            content_type=file.content_type or "application/octet-stream",
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.get("/buckets/{bucket_id}/download/{key:path}", summary="Download object")
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


@router.delete("/buckets/{bucket_id}/objects/{key:path}", summary="Delete object")
async def delete_object(bucket_id: str, key: str,
                        project_id: str = Depends(require_project)):
    try:
        await service.delete_object(project_id, bucket_id, key)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}
