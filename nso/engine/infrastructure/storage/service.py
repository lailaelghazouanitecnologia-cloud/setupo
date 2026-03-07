import logging
import secrets
from datetime import datetime, timezone

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, NsoError
from nso.config import settings
from nso.engine.storage.service import R2Client

logger = logging.getLogger("nso.infrastructure.storage")

# User storage lives under _user_storage/ prefix in R2 to isolate from .zar packages
_PREFIX = "_user_storage"


def _gen_id() -> str:
    return f"bkt_{secrets.token_hex(8)}"


def _r2() -> R2Client:
    return R2Client(settings.r2_config())


def _bucket_prefix(project_id: str, bucket_name: str) -> str:
    """R2 key prefix for a user bucket."""
    return f"{_PREFIX}/{project_id}/{bucket_name}/"


# ── Bucket CRUD ──────────────────────────────────────────────────

async def create_bucket(project_id: str, name: str, public_access: bool = False) -> dict:
    # Validate bucket name
    if not name or len(name) < 2 or len(name) > 63:
        raise NsoError(400, "Bucket name must be 2-63 characters")
    if not all(c.isalnum() or c in "-_" for c in name):
        raise NsoError(400, "Bucket name can only contain letters, numbers, hyphens, underscores")

    existing = await db.fetch_all("storage_buckets", project_id=project_id, name=name)
    if existing:
        raise ConflictError(f"Bucket '{name}' already exists")

    bucket_id = _gen_id()
    r2_prefix = _bucket_prefix(project_id, name)

    record = {
        "id": bucket_id,
        "project_id": project_id,
        "name": name,
        "r2_prefix": r2_prefix,
        "size_bytes": 0,
        "object_count": 0,
        "public_access": 1 if public_access else 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("storage_buckets", record)
    logger.info("Created bucket %s (%s) for project %s", name, bucket_id, project_id)
    return record


async def list_buckets(project_id: str) -> list[dict]:
    return await db.fetch_all("storage_buckets", project_id=project_id)


async def get_bucket(project_id: str, bucket_id: str) -> dict:
    record = await db.fetch_one("storage_buckets", id=bucket_id)
    if not record or record.get("project_id") != project_id:
        raise NotFoundError("Bucket", bucket_id)
    return record


async def delete_bucket(project_id: str, bucket_id: str):
    bucket = await get_bucket(project_id, bucket_id)

    # Delete all objects in the bucket from R2
    r2 = _r2()
    try:
        keys = await r2.list_keys(bucket["r2_prefix"])
        for key in keys:
            await r2.delete(key)
    except Exception as e:
        logger.warning("Failed to clean R2 objects for bucket %s: %s", bucket_id, e)
    finally:
        await r2.close()

    await db.delete("storage_buckets", bucket_id)
    logger.info("Deleted bucket %s", bucket_id)


# ── Object operations ────────────────────────────────────────────

async def list_objects(project_id: str, bucket_id: str, prefix: str = "") -> list[dict]:
    bucket = await get_bucket(project_id, bucket_id)
    r2 = _r2()
    try:
        full_prefix = bucket["r2_prefix"] + prefix
        keys = await r2.list_keys(full_prefix)
        objects = []
        for key in keys:
            # Strip the bucket prefix to get relative path
            relative_key = key[len(bucket["r2_prefix"]):]
            if relative_key:
                objects.append({"key": relative_key, "full_key": key})
        return objects
    finally:
        await r2.close()


async def upload_object(project_id: str, bucket_id: str, key: str,
                        data: bytes, content_type: str = "application/octet-stream") -> dict:
    bucket = await get_bucket(project_id, bucket_id)

    # Enforce key safety (no path traversal)
    if ".." in key or key.startswith("/"):
        raise NsoError(400, "Invalid object key")

    full_key = bucket["r2_prefix"] + key
    r2 = _r2()
    try:
        ok = await r2.upload(full_key, data, content_type)
        if not ok:
            raise NsoError(500, "Upload failed")
    finally:
        await r2.close()

    # Update bucket stats
    await _refresh_bucket_stats(project_id, bucket_id)

    logger.info("Uploaded %s to bucket %s (%d bytes)", key, bucket_id, len(data))
    return {"key": key, "size": len(data), "content_type": content_type}


async def download_object(project_id: str, bucket_id: str, key: str) -> bytes | None:
    bucket = await get_bucket(project_id, bucket_id)
    full_key = bucket["r2_prefix"] + key
    r2 = _r2()
    try:
        return await r2.download(full_key)
    finally:
        await r2.close()


async def delete_object(project_id: str, bucket_id: str, key: str):
    bucket = await get_bucket(project_id, bucket_id)
    full_key = bucket["r2_prefix"] + key
    r2 = _r2()
    try:
        await r2.delete(full_key)
    finally:
        await r2.close()

    await _refresh_bucket_stats(project_id, bucket_id)
    logger.info("Deleted %s from bucket %s", key, bucket_id)


async def _refresh_bucket_stats(project_id: str, bucket_id: str):
    """Update cached size and object count for a bucket."""
    bucket = await get_bucket(project_id, bucket_id)
    r2 = _r2()
    try:
        keys = await r2.list_keys(bucket["r2_prefix"])
        await db.update("storage_buckets", bucket_id, {
            "object_count": len(keys),
        })
    except Exception as e:
        logger.warning("Failed to refresh stats for bucket %s: %s", bucket_id, e)
    finally:
        await r2.close()
