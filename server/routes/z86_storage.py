"""
z86 storage management routes — central server proxy to z86 service.

Two routers:
  - project_router: project-scoped (mounted at /api/projects/{pid}/z86)
  - admin_router: admin-only (mounted at /api/admin/z86)
"""
import logging
import secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from server.config import settings
from server.core import db
from server.deps import require_admin, require_project
from server.auth.middleware import AuthContext

logger = logging.getLogger("nso.z86")

project_router = APIRouter()
admin_router = APIRouter()

Z86_TIMEOUT = 60.0


def _z86_url(path: str) -> str:
    return f"{settings.Z86_ENDPOINT.rstrip('/')}{path}"


def _z86_headers() -> dict:
    return {"Authorization": f"Bearer {settings.Z86_ADMIN_TOKEN}"}


async def _z86_request(method: str, path: str, **kwargs) -> httpx.Response:
    if not settings.Z86_ENDPOINT:
        raise HTTPException(503, "z86 storage not configured")
    async with httpx.AsyncClient(timeout=Z86_TIMEOUT) as client:
        resp = await client.request(method, _z86_url(path), headers=_z86_headers(), **kwargs)
    if resp.status_code >= 400:
        logger.error("z86 %s %s → %d: %s", method, path, resp.status_code, resp.text[:200])
    return resp


# ── Provisioning (called internally) ──────────────────────

async def provision_z86_for_project(project_id: str) -> dict | None:
    """Create z86 bucket + access key for a project. Returns key info or None."""
    if not settings.Z86_ENDPOINT:
        return None

    bucket_name = f"proj-{project_id}"

    resp = await _z86_request("POST", "/admin/buckets", json={
        "name": bucket_name,
        "owner_id": project_id,
    })
    if resp.status_code not in (200, 409):
        logger.error("Failed to create z86 bucket for project %s", project_id)
        return None

    resp = await _z86_request("POST", "/admin/keys", json={
        "owner_id": project_id,
        "owner_type": "project",
        "label": f"project-{project_id}",
        "allowed_buckets": [bucket_name],
    })
    if resp.status_code != 200:
        logger.error("Failed to create z86 key for project %s", project_id)
        return None

    key_data = resp.json()
    now = datetime.now(timezone.utc).isoformat()
    await db.insert("z86_keys", {
        "id": f"z86k_{secrets.token_hex(8)}",
        "project_id": project_id,
        "access_key_id": key_data["access_key_id"],
        "secret_access_key": key_data["secret_access_key"],
        "label": key_data.get("label", ""),
        "active": 1,
        "bucket": bucket_name,
        "created_at": now,
    })

    logger.info("Provisioned z86 for project %s: bucket=%s", project_id, bucket_name)
    return {
        "bucket": bucket_name,
        "access_key_id": key_data["access_key_id"],
        "secret_access_key": key_data["secret_access_key"],
        "endpoint": settings.Z86_ENDPOINT,
    }


# ── Project-scoped routes ─────────────────────────────────

@project_router.get("/storage")
async def get_project_storage(project_id: str = Depends(require_project)):
    """Get z86 storage info for a project."""
    keys = await db.fetch_all("z86_keys", project_id=project_id)
    if not keys:
        return {"configured": False, "message": "No z86 storage provisioned"}

    bucket_name = keys[0]["bucket"]
    stats = {}
    try:
        resp = await _z86_request("GET", f"/admin/buckets/{bucket_name}")
        if resp.status_code == 200:
            stats = resp.json()
    except Exception:
        pass

    return {
        "configured": True,
        "endpoint": settings.Z86_ENDPOINT,
        "bucket": bucket_name,
        "access_key_id": keys[0]["access_key_id"],
        "stats": stats,
        "keys": [{
            "id": k["id"],
            "access_key_id": k["access_key_id"],
            "label": k["label"],
            "active": k["active"],
            "created_at": k["created_at"],
        } for k in keys],
    }


@project_router.post("/storage/provision")
async def provision_storage(
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_admin),
):
    """Provision z86 storage for a project (admin)."""
    existing = await db.fetch_all("z86_keys", project_id=project_id)
    if existing:
        raise HTTPException(409, "z86 storage already provisioned")
    result = await provision_z86_for_project(project_id)
    if not result:
        raise HTTPException(503, "Failed to provision z86 storage")
    return result


@project_router.post("/storage/keys/rotate")
async def rotate_storage_key(
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_admin),
):
    """Rotate z86 access key for a project (admin)."""
    keys = await db.fetch_all("z86_keys", project_id=project_id)
    if not keys:
        raise HTTPException(404, "No z86 storage provisioned")

    old_key = keys[0]
    bucket_name = old_key["bucket"]

    try:
        await _z86_request("DELETE", f"/admin/keys/{old_key['id']}")
    except Exception:
        pass

    resp = await _z86_request("POST", "/admin/keys", json={
        "owner_id": project_id,
        "owner_type": "project",
        "label": f"project-{project_id}-rotated",
        "allowed_buckets": [bucket_name],
    })
    if resp.status_code != 200:
        raise HTTPException(502, "Failed to create new z86 key")

    key_data = resp.json()
    now = datetime.now(timezone.utc).isoformat()

    await db.update("z86_keys", old_key["id"], {"active": 0})
    await db.insert("z86_keys", {
        "id": f"z86k_{secrets.token_hex(8)}",
        "project_id": project_id,
        "access_key_id": key_data["access_key_id"],
        "secret_access_key": key_data["secret_access_key"],
        "label": key_data.get("label", ""),
        "active": 1,
        "bucket": bucket_name,
        "created_at": now,
    })

    return {
        "ok": True,
        "access_key_id": key_data["access_key_id"],
        "secret_access_key": key_data["secret_access_key"],
    }


# ── Admin routes ──────────────────────────────────────────

@admin_router.get("/overview")
async def z86_overview(auth: AuthContext = Depends(require_admin)):
    """z86 cluster overview."""
    if not settings.Z86_ENDPOINT:
        return {"configured": False}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            health_resp = await client.get(f"{settings.Z86_ENDPOINT.rstrip('/')}/health")
        health = health_resp.json() if health_resp.status_code == 200 else {}

        stats_resp = await _z86_request("GET", "/admin/stats")
        stats = stats_resp.json() if stats_resp.status_code == 200 else {}

        buckets_resp = await _z86_request("GET", "/admin/buckets")
        buckets = buckets_resp.json() if buckets_resp.status_code == 200 else []

        keys_resp = await _z86_request("GET", "/admin/keys")
        keys = keys_resp.json() if keys_resp.status_code == 200 else []

    except httpx.ConnectError:
        return {"configured": True, "endpoint": settings.Z86_ENDPOINT, "status": "unreachable"}

    return {
        "configured": True,
        "endpoint": settings.Z86_ENDPOINT,
        "health": health,
        "stats": stats,
        "buckets": buckets,
        "total_keys": len(keys),
    }


@admin_router.get("/buckets")
async def list_all_buckets(auth: AuthContext = Depends(require_admin)):
    """List all z86 buckets."""
    resp = await _z86_request("GET", "/admin/buckets")
    if resp.status_code != 200:
        raise HTTPException(502, "Failed to list buckets")
    return resp.json()


@admin_router.get("/buckets/{bucket}/objects")
async def list_bucket_objects(
    bucket: str,
    prefix: str = "",
    auth: AuthContext = Depends(require_admin),
):
    """Browse objects in a z86 bucket."""
    resp = await _z86_request("GET", f"/admin/buckets/{bucket}/objects", params={"prefix": prefix})
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Failed to list objects")
    return resp.json()


@admin_router.delete("/buckets/{bucket}/objects/{key:path}")
async def delete_object(
    bucket: str,
    key: str,
    auth: AuthContext = Depends(require_admin),
):
    """Delete an object from z86."""
    resp = await _z86_request("DELETE", f"/admin/buckets/{bucket}/objects/{key}")
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Failed to delete object")
    return resp.json()
