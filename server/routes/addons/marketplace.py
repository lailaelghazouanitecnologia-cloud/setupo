"""NSO Addons — Marketplace-specific API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from server.core import db
from server.deps import require_project

logger = logging.getLogger("nso.addons.marketplace")
router = APIRouter()


async def _require_marketplace_app(project_id: str, app_id: str):
    """Check that a marketplace app is installed and enabled."""
    addon = await db.fetch_one("addons", project_id=project_id, addon_id=app_id, addon_type="marketplace")
    if not addon or not addon.get("enabled"):
        raise HTTPException(403, f"Marketplace app '{app_id}' is not installed or is disabled")
    return addon


@router.get("/{app_id}/status")
async def marketplace_app_status(app_id: str, project_id: str = Depends(require_project)):
    """Get the status of an installed marketplace app."""
    addon = await _require_marketplace_app(project_id, app_id)

    return {
        "app_id": app_id,
        "name": addon["name"],
        "version": addon["version"],
        "enabled": addon["enabled"],
        "config": addon.get("config", {}),
        "installed_at": addon.get("installed_at"),
    }
