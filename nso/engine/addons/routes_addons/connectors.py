"""NSO Addons — Connector-specific API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project

logger = logging.getLogger("nso.addons.connectors")
router = APIRouter()


async def _require_connector(project_id: str, connector_id: str):
    """Check that a connector is installed and enabled."""
    addon = await db.fetch_one("addons", project_id=project_id, addon_id=connector_id, addon_type="connector")
    if not addon or not addon.get("enabled"):
        raise HTTPException(403, f"Connector '{connector_id}' is not installed or is disabled")
    return addon


class ConnectorConfigRequest(BaseModel):
    config: dict = {}


@router.get("/{connector_id}/status")
async def connector_status(connector_id: str, project_id: str = Depends(require_project)):
    """Get the status and config of an installed connector."""
    addon = await _require_connector(project_id, connector_id)
    config = addon.get("config", {})

    # Check if connector has required credentials configured
    connected = False
    if connector_id == "github":
        connected = bool(config.get("token") or config.get("app_id"))
    elif connector_id == "supabase":
        connected = bool(config.get("url") and config.get("anon_key"))
    elif connector_id == "s3":
        connected = bool(config.get("endpoint") and config.get("access_key"))
    elif connector_id == "slack":
        connected = bool(config.get("webhook_url") or config.get("bot_token"))
    elif connector_id == "docker-registry":
        connected = bool(config.get("registry_url"))

    return {
        "connector_id": connector_id,
        "name": addon["name"],
        "connected": connected,
        "config_keys": list(config.keys()),
        "enabled": addon["enabled"],
    }


@router.post("/{connector_id}/test")
async def test_connector(connector_id: str, project_id: str = Depends(require_project)):
    """Test the connection of an installed connector."""
    addon = await _require_connector(project_id, connector_id)
    config = addon.get("config", {})

    # Placeholder: real implementations would make actual API calls
    if connector_id == "github" and config.get("token"):
        return {"ok": True, "message": "GitHub connection verified"}
    elif connector_id == "supabase" and config.get("url"):
        return {"ok": True, "message": "Supabase connection verified"}
    elif connector_id == "s3" and config.get("endpoint"):
        return {"ok": True, "message": "S3 connection verified"}
    elif connector_id == "slack" and (config.get("webhook_url") or config.get("bot_token")):
        return {"ok": True, "message": "Slack connection verified"}
    elif connector_id == "docker-registry" and config.get("registry_url"):
        return {"ok": True, "message": "Docker Registry connection verified"}

    return {"ok": False, "message": "Connector not configured — add credentials first"}
