"""
z86 dashboard API — user-scoped bucket, key, and object management.

These routes are for authenticated z86 users managing their own storage.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from z86 import db, users
from z86.auth import create_access_key, revoke_key
from z86.storage import engine

logger = logging.getLogger("z86.dashboard")

router = APIRouter(prefix="/api")


# ── Overview ───────────────────────────────────────────────

@router.get("/overview")
async def overview(user=Depends(users.require_user)):
    buckets = await engine.list_buckets(user["id"])
    keys = await db.fetch_all("access_keys", owner_id=user["id"])
    total_objects = sum(b.get("object_count", 0) for b in buckets)
    total_size = sum(b.get("total_size", 0) for b in buckets)
    return {
        "buckets": len(buckets),
        "objects": total_objects,
        "storage_used": total_size,
        "storage_limit": user.get("storage_limit", 1073741824),
        "keys": len([k for k in keys if k.get("active")]),
        "plan": user.get("plan", "free"),
    }


# ── Buckets ────────────────────────────────────────────────

@router.get("/buckets")
async def list_buckets(user=Depends(users.require_user)):
    return await engine.list_buckets(user["id"])


@router.post("/buckets")
async def create_bucket(name: str = Form(...), user=Depends(users.require_user)):
    name = name.strip().lower()
    if not name or len(name) < 3 or len(name) > 63:
        raise HTTPException(400, "Bucket name must be 3-63 characters")
    if not all(c.isalnum() or c in "-." for c in name):
        raise HTTPException(400, "Only lowercase alphanumeric, hyphens, and dots")
    # Check bucket limit based on plan
    existing = await engine.list_buckets(user["id"])
    plan_limits = {"free": 3, "pro": 50, "enterprise": 500}
    limit = plan_limits.get(user.get("plan", "free"), 3)
    if len(existing) >= limit:
        raise HTTPException(403, f"Bucket limit reached ({limit} on {user.get('plan', 'free')} plan)")
    ok = await engine.create_bucket(name, user["id"])
    if not ok:
        raise HTTPException(409, f"Bucket '{name}' already exists")
    return {"ok": True, "bucket": name}


@router.get("/buckets/{name}")
async def get_bucket(name: str, user=Depends(users.require_user)):
    bucket = await engine.get_bucket(name)
    if not bucket or bucket["owner_id"] != user["id"]:
        raise HTTPException(404, "Bucket not found")
    return bucket


@router.delete("/buckets/{name}")
async def delete_bucket(name: str, user=Depends(users.require_user)):
    bucket = await db.fetch_one("buckets", name=name)
    if not bucket or bucket["owner_id"] != user["id"]:
        raise HTTPException(404, "Bucket not found")
    ok = await engine.delete_bucket(name)
    if not ok:
        raise HTTPException(400, "Bucket not empty — delete all objects first")
    return {"ok": True}


# ── Objects ────────────────────────────────────────────────

@router.get("/buckets/{bucket}/objects")
async def list_objects(
    bucket: str,
    prefix: str = "",
    max_keys: int = 100,
    user=Depends(users.require_user),
):
    b = await db.fetch_one("buckets", name=bucket)
    if not b or b["owner_id"] != user["id"]:
        raise HTTPException(404, "Bucket not found")
    return await engine.list_objects(bucket, prefix=prefix, max_keys=max_keys)


@router.post("/buckets/{bucket}/upload")
async def upload_object(
    bucket: str,
    key: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(users.require_user),
):
    b = await db.fetch_one("buckets", name=bucket)
    if not b or b["owner_id"] != user["id"]:
        raise HTTPException(404, "Bucket not found")
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    try:
        result = await engine.put_object(bucket, key, data, content_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@router.delete("/buckets/{bucket}/objects/{key:path}")
async def delete_object(bucket: str, key: str, user=Depends(users.require_user)):
    b = await db.fetch_one("buckets", name=bucket)
    if not b or b["owner_id"] != user["id"]:
        raise HTTPException(404, "Bucket not found")
    ok = await engine.delete_object(bucket, key)
    if not ok:
        raise HTTPException(404, "Object not found")
    return {"ok": True}


# ── Access Keys ────────────────────────────────────────────

@router.get("/keys")
async def list_keys(user=Depends(users.require_user)):
    keys = await db.fetch_all("access_keys", owner_id=user["id"])
    for k in keys:
        k.pop("secret_key", None)
        k.pop("secret_hash", None)
    return keys


@router.post("/keys")
async def create_key(
    label: str = Form(""),
    allowed_buckets: str = Form(""),
    user=Depends(users.require_user),
):
    # Limit keys per user
    existing = await db.fetch_all("access_keys", owner_id=user["id"])
    active_keys = [k for k in existing if k.get("active")]
    plan_limits = {"free": 2, "pro": 10, "enterprise": 100}
    limit = plan_limits.get(user.get("plan", "free"), 2)
    if len(active_keys) >= limit:
        raise HTTPException(403, f"Key limit reached ({limit} on {user.get('plan', 'free')} plan)")
    buckets = [b.strip() for b in allowed_buckets.split(",") if b.strip()] if allowed_buckets else []
    result = await create_access_key(
        owner_id=user["id"],
        owner_type="user",
        label=label,
        allowed_buckets=buckets or None,
    )
    return result


@router.delete("/keys/{key_id}")
async def delete_key(key_id: str, user=Depends(users.require_user)):
    key = await db.fetch_one("access_keys", id=key_id)
    if not key or key["owner_id"] != user["id"]:
        raise HTTPException(404, "Key not found")
    await revoke_key(key_id)
    return {"ok": True}


# ── Usage ──────────────────────────────────────────────────

@router.get("/usage")
async def usage(user=Depends(users.require_user)):
    buckets = await engine.list_buckets(user["id"])
    bucket_usage = []
    for b in buckets:
        bucket_usage.append({
            "bucket": b["name"],
            "objects": b.get("object_count", 0),
            "size": b.get("total_size", 0),
        })
    total_size = sum(b.get("total_size", 0) for b in buckets)
    return {
        "total_storage": total_size,
        "storage_limit": user.get("storage_limit", 1073741824),
        "usage_pct": round(total_size / max(user.get("storage_limit", 1), 1) * 100, 1),
        "buckets": bucket_usage,
    }
