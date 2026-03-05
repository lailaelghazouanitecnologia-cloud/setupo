"""
z86 filesystem storage engine.

Objects are stored as files under:
  /data/z86/buckets/{bucket}/{key}

Metadata is tracked in SQLite (z86/db.py).
"""
import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from z86.config import settings
from z86 import db

logger = logging.getLogger("z86.storage")


class StorageEngine:

    # ── Bucket operations ──────────────────────────────────

    async def create_bucket(self, name: str, owner_id: str) -> bool:
        existing = await db.fetch_one("buckets", name=name)
        if existing:
            return False
        bucket_dir = settings.bucket_path(name)
        bucket_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        await db.insert("buckets", {
            "name": name,
            "owner_id": owner_id,
            "region": "local",
            "created_at": now,
        })
        logger.info("Created bucket: %s (owner: %s)", name, owner_id)
        return True

    async def delete_bucket(self, name: str) -> bool:
        existing = await db.fetch_one("buckets", name=name)
        if not existing:
            return False
        obj_count = await db.count("objects", bucket=name)
        if obj_count > 0:
            return False
        bucket_dir = settings.bucket_path(name)
        if bucket_dir.exists():
            shutil.rmtree(bucket_dir)
        await db.delete("buckets", name=name)
        logger.info("Deleted bucket: %s", name)
        return True

    async def get_bucket(self, name: str) -> dict | None:
        bucket = await db.fetch_one("buckets", name=name)
        if not bucket:
            return None
        stats = await db.query(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total FROM objects WHERE bucket = ?",
            [name],
        )
        bucket["object_count"] = stats[0]["cnt"] if stats else 0
        bucket["total_size"] = stats[0]["total"] if stats else 0
        return bucket

    async def list_buckets(self, owner_id: str | None = None) -> list[dict]:
        if owner_id:
            buckets = await db.fetch_all("buckets", owner_id=owner_id)
        else:
            buckets = await db.fetch_all("buckets")
        for b in buckets:
            stats = await db.query(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total FROM objects WHERE bucket = ?",
                [b["name"]],
            )
            b["object_count"] = stats[0]["cnt"] if stats else 0
            b["total_size"] = stats[0]["total"] if stats else 0
        return buckets

    # ── Object operations ──────────────────────────────────

    async def put_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        bucket_info = await db.fetch_one("buckets", name=bucket)
        if not bucket_info:
            raise ValueError(f"Bucket '{bucket}' does not exist")

        if len(data) > settings.MAX_OBJECT_SIZE:
            raise ValueError(f"Object too large ({len(data)} > {settings.MAX_OBJECT_SIZE})")

        obj_path = settings.object_path(bucket, key)
        obj_path.parent.mkdir(parents=True, exist_ok=True)

        sha = hashlib.sha256(data).hexdigest()
        now = datetime.now(timezone.utc).isoformat()

        # Write file
        obj_path.write_bytes(data)

        # Upsert metadata
        existing = await db.query(
            "SELECT id FROM objects WHERE bucket = ? AND key = ?", [bucket, key]
        )
        if existing:
            await db.update("objects", "id", existing[0]["id"], {
                "size": len(data),
                "content_type": content_type,
                "sha256": sha,
                "updated_at": now,
            })
        else:
            await db.insert("objects", {
                "bucket": bucket,
                "key": key,
                "size": len(data),
                "content_type": content_type,
                "sha256": sha,
                "created_at": now,
                "updated_at": now,
            })

        logger.info("PUT %s/%s (%d bytes)", bucket, key, len(data))
        return {"bucket": bucket, "key": key, "size": len(data), "sha256": sha}

    async def get_object(self, bucket: str, key: str) -> tuple[bytes, dict] | None:
        meta = await db.query(
            "SELECT * FROM objects WHERE bucket = ? AND key = ?", [bucket, key]
        )
        if not meta:
            return None

        obj_path = settings.object_path(bucket, key)
        if not obj_path.exists():
            # Metadata exists but file missing — clean up
            await db.delete("objects", bucket=bucket, key=key)
            return None

        data = obj_path.read_bytes()
        return data, dict(meta[0])

    async def head_object(self, bucket: str, key: str) -> dict | None:
        meta = await db.query(
            "SELECT * FROM objects WHERE bucket = ? AND key = ?", [bucket, key]
        )
        if not meta:
            return None
        return dict(meta[0])

    async def delete_object(self, bucket: str, key: str) -> bool:
        meta = await db.query(
            "SELECT id FROM objects WHERE bucket = ? AND key = ?", [bucket, key]
        )
        if not meta:
            return False

        obj_path = settings.object_path(bucket, key)
        if obj_path.exists():
            obj_path.unlink()

        # Clean up empty parent directories (but not the bucket root)
        bucket_root = settings.bucket_path(bucket)
        parent = obj_path.parent
        while parent != bucket_root and parent.exists():
            try:
                parent.rmdir()  # only removes if empty
                parent = parent.parent
            except OSError:
                break

        await db.delete("objects", bucket=bucket, key=key)
        logger.info("DELETE %s/%s", bucket, key)
        return True

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 1000,
        continuation_token: str = "",
    ) -> dict:
        bucket_info = await db.fetch_one("buckets", name=bucket)
        if not bucket_info:
            raise ValueError(f"Bucket '{bucket}' does not exist")

        if prefix:
            rows = await db.query(
                "SELECT key, size, content_type, sha256, updated_at FROM objects "
                "WHERE bucket = ? AND key LIKE ? ORDER BY key LIMIT ?",
                [bucket, f"{prefix}%", max_keys + 1],
            )
        else:
            rows = await db.query(
                "SELECT key, size, content_type, sha256, updated_at FROM objects "
                "WHERE bucket = ? ORDER BY key LIMIT ?",
                [bucket, max_keys + 1],
            )

        truncated = len(rows) > max_keys
        if truncated:
            rows = rows[:max_keys]

        return {
            "objects": rows,
            "count": len(rows),
            "is_truncated": truncated,
            "prefix": prefix,
        }

    # ── Stats ──────────────────────────────────────────────

    async def stats(self) -> dict:
        bucket_count = await db.count("buckets")
        obj_stats = await db.query(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total FROM objects"
        )
        # Disk usage
        data_dir = settings.DATA_DIR / "buckets"
        disk_used = 0
        if data_dir.exists():
            for dirpath, _, filenames in os.walk(data_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    disk_used += os.path.getsize(fp)

        return {
            "total_buckets": bucket_count,
            "total_objects": obj_stats[0]["cnt"],
            "total_size_bytes": obj_stats[0]["total"],
            "disk_used_bytes": disk_used,
        }


engine = StorageEngine()
