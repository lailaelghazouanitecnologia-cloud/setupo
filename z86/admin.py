"""
z86 admin API — bucket management, access keys, stats.

These endpoints use Bearer token auth (Z86_ADMIN_TOKEN),
NOT AWS4 signatures. Used by the NSO central server.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from z86 import db
from z86.auth import create_access_key, revoke_key
from z86.config import settings
from z86.models import CreateKeyRequest, CreateBucketRequest
from z86.storage import engine

logger = logging.getLogger("z86.admin")

router = APIRouter(prefix="/admin")


async def require_admin(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
    if not token or not settings.ADMIN_TOKEN or token != settings.ADMIN_TOKEN:
        raise HTTPException(403, "Admin access required")
    return True


# ── Stats ──────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(_=Depends(require_admin)):
    return await engine.stats()


# ── Buckets ────────────────────────────────────────────────

@router.get("/buckets")
async def list_buckets(owner_id: str = "", _=Depends(require_admin)):
    return await engine.list_buckets(owner_id or None)


@router.post("/buckets")
async def create_bucket(req: CreateBucketRequest, _=Depends(require_admin)):
    name = req.name.strip().lower()
    if not name or len(name) < 3 or len(name) > 63:
        raise HTTPException(400, "Bucket name must be 3-63 characters")
    if not all(c.isalnum() or c in "-." for c in name):
        raise HTTPException(400, "Bucket name: only lowercase alphanumeric, hyphens, dots")
    ok = await engine.create_bucket(name, req.owner_id)
    if not ok:
        raise HTTPException(409, f"Bucket '{name}' already exists")
    return {"ok": True, "bucket": name}


@router.get("/buckets/{name}")
async def get_bucket(name: str, _=Depends(require_admin)):
    bucket = await engine.get_bucket(name)
    if not bucket:
        raise HTTPException(404, "Bucket not found")
    return bucket


@router.delete("/buckets/{name}")
async def delete_bucket(name: str, _=Depends(require_admin)):
    ok = await engine.delete_bucket(name)
    if not ok:
        raise HTTPException(400, "Bucket not found or not empty")
    return {"ok": True}


# ── Access Keys ────────────────────────────────────────────

@router.get("/keys")
async def list_keys(owner_id: str = "", _=Depends(require_admin)):
    if owner_id:
        keys = await db.fetch_all("access_keys", owner_id=owner_id)
    else:
        keys = await db.fetch_all("access_keys")
    # Don't expose secret keys in list
    for k in keys:
        k.pop("secret_key", None)
        k.pop("secret_hash", None)
    return keys


@router.post("/keys")
async def create_key(req: CreateKeyRequest, _=Depends(require_admin)):
    result = await create_access_key(
        owner_id=req.owner_id,
        owner_type=req.owner_type,
        label=req.label,
        allowed_buckets=req.allowed_buckets,
    )
    return result


@router.delete("/keys/{key_id}")
async def delete_key(key_id: str, _=Depends(require_admin)):
    key = await db.fetch_one("access_keys", id=key_id)
    if not key:
        raise HTTPException(404, "Key not found")
    await revoke_key(key_id)
    return {"ok": True, "key_id": key_id}


# ── Objects (admin browse) ────────────────────────────────

@router.get("/buckets/{bucket}/objects")
async def list_bucket_objects(
    bucket: str,
    prefix: str = "",
    max_keys: int = 500,
    _=Depends(require_admin),
):
    try:
        return await engine.list_objects(bucket, prefix=prefix, max_keys=max_keys)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/buckets/{bucket}/objects/{key:path}")
async def delete_object(bucket: str, key: str, _=Depends(require_admin)):
    ok = await engine.delete_object(bucket, key)
    if not ok:
        raise HTTPException(404, "Object not found")
    return {"ok": True}
