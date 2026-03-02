"""
Routes for nso-ready pre-compiled system and user app images.

Admin endpoints:
  POST /api/ready/build         — Build + upload system .zar to nso-ready
  GET  /api/ready/versions      — List system versions
  GET  /api/ready/latest        — Get latest system manifest

Project endpoints:
  POST /api/projects/{pid}/ready/freeze     — Freeze user app
  GET  /api/projects/{pid}/ready/versions   — List frozen versions
  GET  /api/projects/{pid}/ready/latest     — Get frozen app manifest
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from server.deps import require_admin, require_project
from server.core.ready import (
    build_and_upload_system,
    get_system_manifest,
    list_system_versions,
    system_ready_exists,
    freeze_user_app,
    get_user_ready_manifest,
    list_user_ready_versions,
    user_ready_exists,
)

logger = logging.getLogger("nso.routes.ready")

# ── System-level routes (admin only) ──

admin_router = APIRouter()


@admin_router.post("/build")
async def build_system(version: str = "", _=Depends(require_admin)):
    """Build NSO platform .zar and upload to nso-ready bucket."""
    try:
        manifest = await build_and_upload_system(version or None)
    except Exception as e:
        logger.error("System build failed: %s", e)
        raise HTTPException(500, f"Build failed: {e}")
    return {"ok": True, "manifest": manifest}


@admin_router.get("/versions")
async def system_versions(_=Depends(require_admin)):
    """List all pre-built system versions."""
    versions = await list_system_versions()
    exists = await system_ready_exists()
    return {"versions": versions, "has_latest": exists}


@admin_router.get("/latest")
async def system_latest(_=Depends(require_admin)):
    """Get the latest system build manifest."""
    manifest = await get_system_manifest()
    if not manifest:
        raise HTTPException(404, "No system build found. Run POST /api/ready/build first.")
    return manifest


# ── User-level routes (project API key or admin) ──

project_router = APIRouter()


@project_router.post("/freeze")
async def freeze_app(
    workspace: str = Query(..., description="Workspace name to freeze"),
    version: str = "",
    project_id: str = Depends(require_project),
):
    """Freeze a deployed user app for instant future deploys."""
    try:
        manifest = await freeze_user_app(project_id, workspace, version or None)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("Freeze failed for %s/%s: %s", project_id, workspace, e)
        raise HTTPException(500, f"Freeze failed: {e}")
    return {"ok": True, "manifest": manifest}


@project_router.get("/versions")
async def user_versions(
    workspace: str = Query(...),
    project_id: str = Depends(require_project),
):
    """List frozen versions for a user app."""
    versions = await list_user_ready_versions(project_id, workspace)
    exists = await user_ready_exists(project_id, workspace)
    return {"workspace": workspace, "versions": versions, "has_latest": exists}


@project_router.get("/latest")
async def user_latest(
    workspace: str = Query(...),
    project_id: str = Depends(require_project),
):
    """Get the latest frozen app manifest."""
    manifest = await get_user_ready_manifest(project_id, workspace)
    if not manifest:
        raise HTTPException(404, f"No frozen build for workspace '{workspace}'")
    return manifest
