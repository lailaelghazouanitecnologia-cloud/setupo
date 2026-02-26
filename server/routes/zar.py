"""Zar routes — Pack, push, deploy, branch, merge workspace .zar packages.

The hot-update flow: pack → push to R2 → tell the agent on the VPS to pull.
No SSH. No instance recreation. The agent handles everything.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from core import db
from core.models import R2Config, ZarManifest, ZarUploadResult
from core.zar.packer import pack, read_manifest
from core.zar.storage import R2Client
from core.workspace_config import read_config, read_package_config
from server.config import settings
from server.deps import require_project

logger = logging.getLogger("setupo.routes.zar")
router = APIRouter()


def _get_r2() -> R2Client:
    """Get R2 client from server settings."""
    cfg = settings.r2_config()
    if not cfg.endpoint:
        raise HTTPException(503, "R2 not configured. Set R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.")
    return R2Client(cfg)


async def _get_agent_url(instance_id: str, project_id: str) -> str:
    """Get the agent HTTP URL for an instance."""
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst:
        raise HTTPException(404, f"Instance {instance_id} not found")
    if inst.get("project_id") != project_id:
        raise HTTPException(403, "Instance does not belong to this project")
    ip = inst.get("ip")
    if not ip:
        raise HTTPException(400, "Instance has no IP yet")
    return f"http://{ip}:8081"


async def _get_agent_token(agent_url: str) -> str:
    """Login to the agent and get a JWT token."""
    admin_email = settings.ADMIN_EMAIL
    # Use the agent's default password — in production this should be per-instance
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{agent_url}/auth/login", json={
            "email": admin_email,
            "password": "dragonmaks321",
        })
    if resp.status_code != 200:
        raise HTTPException(502, f"Agent auth failed: {resp.status_code}")
    return resp.json()["token"]


# ── Pack ─────────────────────────────────────────────────────────

class PackRequest:
    pass  # No body needed, workspace name is in the path


@router.post("/{name}/pack")
async def pack_workspace(name: str, project_id: str = Depends(require_project)):
    """Pack a workspace into a .zar file and return metadata.

    Does NOT upload to R2 — use /push or /ship for that.
    """
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    pkg_config = read_package_config(ws_path)
    version = pkg_config.version if pkg_config else None
    branch = pkg_config.branch if pkg_config else "main"

    zar_bytes, manifest = pack(
        workspace_path=ws_path,
        version=version,
        branch=branch,
        project_id=project_id,
    )

    return {
        "ok": True,
        "manifest": manifest.model_dump(),
        "size": len(zar_bytes),
    }


# ── Push (pack + upload to R2) ──────────────────────────────────

@router.post("/{name}/push")
async def push_workspace(name: str, branch: str = "main", project_id: str = Depends(require_project)):
    """Pack workspace and upload .zar to R2.

    Stores as: {project_id}/{name}/{branch}/v{version}.zar + latest.zar
    """
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    pkg_config = read_package_config(ws_path)
    version = pkg_config.version if pkg_config else None

    zar_bytes, manifest = pack(
        workspace_path=ws_path,
        version=version,
        branch=branch,
        project_id=project_id,
    )

    r2 = _get_r2()
    try:
        key = await r2.upload_zar(project_id, name, branch, manifest.version, zar_bytes)
    finally:
        await r2.close()

    return ZarUploadResult(
        name=name,
        version=manifest.version,
        branch=branch,
        hash=manifest.hash,
        r2_key=key,
        size=len(zar_bytes),
    ).model_dump()


# ── Deploy (tell agent to pull from R2) ─────────────────────────

from pydantic import BaseModel


class DeployZarRequest(BaseModel):
    branch: str = "main"
    version: str = ""           # Empty = latest
    instance_id: str = ""       # Empty = from config.toml


@router.post("/{name}/deploy")
async def deploy_workspace_zar(
    name: str,
    req: DeployZarRequest,
    project_id: str = Depends(require_project),
):
    """Deploy a .zar from R2 to an instance via the agent.

    The agent downloads from R2, snapshots current, extracts, installs deps,
    and restarts the service. No SSH. No instance recreation.
    """
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    # Determine instance
    instance_id = req.instance_id or ws.get("instance_id")
    if not instance_id:
        config = read_config(ws.get("path", ""))
        if config:
            instance_id = config.deploy.instance_id
    if not instance_id:
        raise HTTPException(400, "No instance_id specified and none in config.toml")

    # Build R2 key
    r2_cfg = settings.r2_config()
    if req.version:
        r2_key = f"{project_id}/{name}/{req.branch}/v{req.version}.zar"
    else:
        r2_key = f"{project_id}/{name}/{req.branch}/latest.zar"

    # Verify the .zar exists in R2
    r2 = _get_r2()
    try:
        exists = await r2.exists(r2_key)
        if not exists:
            raise HTTPException(404, f"Package not found in R2: {r2_key}. Run /push first.")
    finally:
        await r2.close()

    # Get agent URL and token
    agent_url = await _get_agent_url(instance_id, project_id)
    token = await _get_agent_token(agent_url)

    # Tell the agent to pull and deploy
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{agent_url}/deploy/pull",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "r2_key": r2_key,
                "r2_endpoint": r2_cfg.endpoint,
                "r2_bucket": r2_cfg.bucket,
                "r2_access_key_id": r2_cfg.access_key_id,
                "r2_secret_access_key": r2_cfg.secret_access_key,
                "target_dir": "/opt/app",
                "restart_service": "setupo-app",
                "install_deps": True,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Agent deploy failed: {resp.status_code} {resp.text[:500]}")

    result = resp.json()

    # Update instance state
    await db.update("instances", instance_id, {
        "state": "running",
        "workspace": name,
    })

    return {
        "ok": True,
        "workspace": name,
        "branch": req.branch,
        "version": result.get("version", ""),
        "snapshot": result.get("snapshot", ""),
        "instance_id": instance_id,
        "message": "Deployed via agent. No SSH. No rebuild.",
    }


# ── Ship (pack + push + deploy in one call) ─────────────────────

class ShipRequest(BaseModel):
    branch: str = "main"
    instance_id: str = ""


@router.post("/{name}/ship")
async def ship_workspace(
    name: str,
    req: ShipRequest,
    project_id: str = Depends(require_project),
):
    """Pack + push to R2 + deploy to instance. One command does it all."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    pkg_config = read_package_config(ws_path)
    version = pkg_config.version if pkg_config else None

    # 1. Pack
    zar_bytes, manifest = pack(
        workspace_path=ws_path,
        version=version,
        branch=req.branch,
        project_id=project_id,
    )

    # 2. Push to R2
    r2 = _get_r2()
    try:
        r2_key = await r2.upload_zar(project_id, name, req.branch, manifest.version, zar_bytes)
    finally:
        await r2.close()

    # 3. Deploy via agent
    instance_id = req.instance_id or ws.get("instance_id")
    if not instance_id:
        config = read_config(ws_path)
        if config:
            instance_id = config.deploy.instance_id
    if not instance_id:
        raise HTTPException(400, "No instance_id specified")

    r2_cfg = settings.r2_config()
    agent_url = await _get_agent_url(instance_id, project_id)
    token = await _get_agent_token(agent_url)

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{agent_url}/deploy/pull",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "r2_key": r2_key,
                "r2_endpoint": r2_cfg.endpoint,
                "r2_bucket": r2_cfg.bucket,
                "r2_access_key_id": r2_cfg.access_key_id,
                "r2_secret_access_key": r2_cfg.secret_access_key,
                "target_dir": "/opt/app",
                "restart_service": "setupo-app",
                "install_deps": True,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Agent deploy failed: {resp.status_code} {resp.text[:500]}")

    result = resp.json()
    await db.update("instances", instance_id, {"state": "running", "workspace": name})

    return {
        "ok": True,
        "action": "ship",
        "workspace": name,
        "version": manifest.version,
        "branch": req.branch,
        "hash": manifest.hash,
        "r2_key": r2_key,
        "size": len(zar_bytes),
        "instance_id": instance_id,
        "snapshot": result.get("snapshot", ""),
        "message": "Packed → pushed to R2 → deployed via agent.",
    }


# ── Rollback ─────────────────────────────────────────────────────

class RollbackRequest(BaseModel):
    instance_id: str
    snapshot: str = ""          # Empty = latest snapshot


@router.post("/{name}/rollback")
async def rollback_workspace(
    name: str,
    req: RollbackRequest,
    project_id: str = Depends(require_project),
):
    """Rollback to a previous snapshot on the instance."""
    agent_url = await _get_agent_url(req.instance_id, project_id)
    token = await _get_agent_token(agent_url)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{agent_url}/deploy/rollback",
            headers={"Authorization": f"Bearer {token}"},
            params={"target_dir": "/opt/app", "restart_service": "setupo-app"},
            json={"snapshot": req.snapshot},
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Agent rollback failed: {resp.text[:500]}")

    return resp.json()


# ── Branch ───────────────────────────────────────────────────────

class BranchRequest(BaseModel):
    name: str                   # New branch name
    from_branch: str = "main"


@router.post("/{name}/branch")
async def create_branch(
    name: str,
    req: BranchRequest,
    project_id: str = Depends(require_project),
):
    """Create a new branch by copying latest .zar from another branch."""
    r2 = _get_r2()
    try:
        key = await r2.copy_branch(project_id, name, req.from_branch, req.name)
    finally:
        await r2.close()

    if not key:
        raise HTTPException(404, f"No .zar found on branch '{req.from_branch}' to copy")

    return {"ok": True, "branch": req.name, "from": req.from_branch, "r2_key": key}


# ── Merge ────────────────────────────────────────────────────────

class MergeRequest(BaseModel):
    from_branch: str
    to_branch: str = "main"


@router.post("/{name}/merge")
async def merge_branch(
    name: str,
    req: MergeRequest,
    project_id: str = Depends(require_project),
):
    """Merge: copy latest .zar from one branch to another as new version."""
    r2 = _get_r2()
    try:
        # Get the latest from source branch
        zar_bytes = await r2.download_zar(project_id, name, req.from_branch)
        if not zar_bytes:
            raise HTTPException(404, f"No .zar on branch '{req.from_branch}'")

        # Get current version on target branch to bump
        versions = await r2.list_versions(project_id, name, req.to_branch)
        manifest = read_manifest(zar_bytes)
        version = manifest.version if manifest else "0.1.0"

        key = await r2.upload_zar(project_id, name, req.to_branch, version, zar_bytes)
    finally:
        await r2.close()

    return {
        "ok": True,
        "merged": f"{req.from_branch} → {req.to_branch}",
        "version": version,
        "r2_key": key,
    }


# ── List versions/branches ──────────────────────────────────────

@router.get("/{name}/versions")
async def list_versions(
    name: str,
    branch: str = "main",
    project_id: str = Depends(require_project),
):
    """List all .zar versions on a branch in R2."""
    r2 = _get_r2()
    try:
        versions = await r2.list_versions(project_id, name, branch)
        branches = await r2.list_branches(project_id, name)
    finally:
        await r2.close()

    return {"workspace": name, "branch": branch, "versions": versions, "branches": branches}


# ── Self-update route (admin only) ──────────────────────────────

class SelfUpdateAPIRequest(BaseModel):
    instance_id: str
    component: str              # "agent" | "frontend" | "core"
    r2_key: str = ""            # If empty, uses latest for the component


@router.post("/self-update")
async def self_update_instance(
    req: SelfUpdateAPIRequest,
    project_id: str = Depends(require_project),
):
    """Push a component update to an instance's agent.

    Components: agent, frontend, core.
    Agent snapshots current, extracts new, restarts briefly.
    """
    r2_cfg = settings.r2_config()

    if not req.r2_key:
        # Default keys for each component
        default_keys = {
            "agent": f"{project_id}/_system/agent/main/latest.zar",
            "frontend": f"{project_id}/_system/frontend/main/latest.zar",
            "core": f"{project_id}/_system/core/main/latest.zar",
        }
        req.r2_key = default_keys.get(req.component, "")

    agent_url = await _get_agent_url(req.instance_id, project_id)
    token = await _get_agent_token(agent_url)

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{agent_url}/deploy/self-update",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "component": req.component,
                "r2_key": req.r2_key,
                "r2_endpoint": r2_cfg.endpoint,
                "r2_bucket": r2_cfg.bucket,
                "r2_access_key_id": r2_cfg.access_key_id,
                "r2_secret_access_key": r2_cfg.secret_access_key,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Self-update failed: {resp.text[:500]}")

    return resp.json()
