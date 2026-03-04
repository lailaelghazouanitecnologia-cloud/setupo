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


# ── Agent proxy (admin only) ─────────────────────────────
# These proxy requests to the z86 agent for remote management

_agent_token_cache: dict[str, str] = {}


async def _get_agent_token() -> str:
    """Get or cache a JWT token from the z86 agent."""
    if "token" in _agent_token_cache:
        return _agent_token_cache["token"]
    if not settings.Z86_AGENT_ENDPOINT or not settings.Z86_AGENT_PASSWORD:
        raise HTTPException(503, "z86 agent not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.Z86_AGENT_ENDPOINT.rstrip('/')}/auth/login",
            json={"email": settings.ADMIN_EMAIL, "password": settings.Z86_AGENT_PASSWORD},
        )
    if resp.status_code != 200:
        raise HTTPException(502, "Failed to authenticate with z86 agent")
    token = resp.json()["token"]
    _agent_token_cache["token"] = token
    return token


async def _agent_request(method: str, path: str, **kwargs) -> httpx.Response:
    if not settings.Z86_AGENT_ENDPOINT:
        raise HTTPException(503, "z86 agent not configured")
    token = await _get_agent_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=Z86_TIMEOUT) as client:
        resp = await client.request(
            method,
            f"{settings.Z86_AGENT_ENDPOINT.rstrip('/')}{path}",
            headers=headers,
            **kwargs,
        )
    # Token expired — retry once
    if resp.status_code == 401:
        _agent_token_cache.clear()
        token = await _get_agent_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=Z86_TIMEOUT) as client:
            resp = await client.request(
                method,
                f"{settings.Z86_AGENT_ENDPOINT.rstrip('/')}{path}",
                headers=headers,
                **kwargs,
            )
    return resp


@admin_router.get("/agent/health")
async def agent_health(auth: AuthContext = Depends(require_admin)):
    """z86 agent health check."""
    if not settings.Z86_AGENT_ENDPOINT:
        return {"configured": False}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.Z86_AGENT_ENDPOINT.rstrip('/')}/health")
        return resp.json() if resp.status_code == 200 else {"status": "error", "code": resp.status_code}
    except httpx.ConnectError:
        return {"status": "unreachable"}


@admin_router.get("/agent/files/list")
async def agent_list_files(path: str = "/opt/nso/z86", auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("GET", "/files/list", params={"path": path})
    return resp.json()


@admin_router.get("/agent/files/read")
async def agent_read_file(path: str = "", auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("GET", "/files/read", params={"path": path})
    return resp.json()


@admin_router.post("/agent/files/write")
async def agent_write_file(data: dict, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("POST", "/files/write", json=data)
    return resp.json()


@admin_router.get("/agent/files/tree")
async def agent_file_tree(path: str = "/opt/nso/z86", depth: int = 3, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("GET", "/files/tree", params={"path": path, "depth": depth})
    return resp.json()


@admin_router.post("/agent/exec")
async def agent_exec(data: dict, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("POST", "/exec/", json=data)
    return resp.json()


@admin_router.post("/agent/exec/service")
async def agent_service(action: str, name: str, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("POST", f"/exec/service?action={action}&name={name}")
    return resp.json()


@admin_router.get("/agent/secrets")
async def agent_list_secrets(auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("GET", "/secrets")
    return resp.json()


@admin_router.post("/agent/secrets")
async def agent_add_secret(data: dict, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("POST", "/secrets", json=data)
    return resp.json()


@admin_router.put("/agent/secrets/{key}")
async def agent_update_secret(key: str, data: dict, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("PUT", f"/secrets/{key}", json=data)
    return resp.json()


@admin_router.delete("/agent/secrets/{key}")
async def agent_delete_secret(key: str, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("DELETE", f"/secrets/{key}")
    return resp.json()


@admin_router.get("/agent/deploy/current")
async def agent_deploy_current(auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("GET", "/deploy/current")
    return resp.json()


@admin_router.post("/agent/deploy/self-update")
async def agent_self_update(data: dict, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("POST", "/deploy/self-update", json=data)
    return resp.json()


@admin_router.post("/agent/deploy/rollback")
async def agent_rollback(data: dict, auth: AuthContext = Depends(require_admin)):
    resp = await _agent_request("POST", "/deploy/rollback", json=data)
    return resp.json()
