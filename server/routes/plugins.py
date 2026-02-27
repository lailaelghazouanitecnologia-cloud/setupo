"""Plugin routes — Install, configure, enable/disable, and uninstall plugins.

Mounted at /api/projects/{project_id}/plugins
"""
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from core import db
from core.models import InstallPluginRequest, UpdatePluginRequest
from server.deps import require_project

logger = logging.getLogger("setupo.routes.plugins")
router = APIRouter()

# ── Plugin catalog ──────────────────────────────────────────────
# Available plugins with metadata. In the future this could come from
# a remote registry, but for now it's defined here.

PLUGIN_CATALOG = {
    "monitoring": {
        "name": "Monitoring",
        "description": "System metrics, alerts, and uptime tracking",
        "version": "1.0.0",
        "category": "observability",
    },
    "backups": {
        "name": "Backups",
        "description": "Automated snapshot and restore for workspaces",
        "version": "1.0.0",
        "category": "data",
    },
    "ci-cd": {
        "name": "CI/CD",
        "description": "Build and deploy pipelines for your projects",
        "version": "0.9.0",
        "category": "devops",
    },
    "logs": {
        "name": "Log Viewer",
        "description": "Centralized log aggregation and search",
        "version": "1.0.0",
        "category": "observability",
    },
    "dns": {
        "name": "DNS Manager",
        "description": "Manage DNS records for your domains",
        "version": "1.0.0",
        "category": "networking",
    },
    "cron": {
        "name": "Cron Jobs",
        "description": "Schedule and manage recurring tasks",
        "version": "1.0.0",
        "category": "automation",
    },
}


# ── List ────────────────────────────────────────────────────────

@router.get("")
async def list_plugins(project_id: str = Depends(require_project)):
    """List all available plugins and their installation status."""
    installed = await db.fetch_all("plugins", project_id=project_id)
    installed_map = {p["plugin_id"]: p for p in installed}

    plugins = []
    for pid, info in PLUGIN_CATALOG.items():
        inst = installed_map.get(pid)
        plugins.append({
            "plugin_id": pid,
            "name": info["name"],
            "description": info["description"],
            "version": info["version"],
            "category": info["category"],
            "installed": inst is not None,
            "enabled": inst["enabled"] if inst else False,
            "config": inst.get("config", {}) if inst else {},
            "installed_at": inst["installed_at"] if inst else None,
            "id": inst["id"] if inst else None,
        })

    return {"plugins": plugins}


# ── Install ─────────────────────────────────────────────────────

@router.post("/install")
async def install_plugin(req: InstallPluginRequest, project_id: str = Depends(require_project)):
    """Install a plugin for this project."""
    if req.plugin_id not in PLUGIN_CATALOG:
        raise HTTPException(404, f"Plugin '{req.plugin_id}' not found in catalog")

    existing = await db.fetch_one("plugins", project_id=project_id, plugin_id=req.plugin_id)
    if existing:
        raise HTTPException(409, f"Plugin '{req.plugin_id}' is already installed")

    info = PLUGIN_CATALOG[req.plugin_id]
    plugin_data = {
        "id": f"plg_{secrets.token_hex(8)}",
        "project_id": project_id,
        "plugin_id": req.plugin_id,
        "name": info["name"],
        "description": info["description"],
        "version": info["version"],
        "category": info["category"],
        "enabled": True,
        "config": req.config,
        "installed_at": datetime.utcnow().isoformat(),
    }
    await db.insert("plugins", plugin_data)

    logger.info("Installed plugin %s for project %s", req.plugin_id, project_id)

    return {
        "ok": True,
        "plugin": {
            **plugin_data,
            "installed": True,
        },
    }


# ── Update (enable/disable, config) ────────────────────────────

@router.patch("/{plugin_id}")
async def update_plugin(plugin_id: str, req: UpdatePluginRequest, project_id: str = Depends(require_project)):
    """Update plugin settings (enable/disable, config)."""
    existing = await db.fetch_one("plugins", project_id=project_id, plugin_id=plugin_id)
    if not existing:
        raise HTTPException(404, f"Plugin '{plugin_id}' is not installed")

    updates = {}
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    if req.config is not None:
        updates["config"] = req.config

    if updates:
        await db.update("plugins", existing["id"], updates)

    return {"ok": True, "plugin_id": plugin_id, "updated": list(updates.keys())}


# ── Uninstall ───────────────────────────────────────────────────

@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str, project_id: str = Depends(require_project)):
    """Uninstall a plugin from this project."""
    existing = await db.fetch_one("plugins", project_id=project_id, plugin_id=plugin_id)
    if not existing:
        raise HTTPException(404, f"Plugin '{plugin_id}' is not installed")

    await db.delete("plugins", existing["id"])

    logger.info("Uninstalled plugin %s from project %s", plugin_id, project_id)

    return {"ok": True, "plugin_id": plugin_id}
