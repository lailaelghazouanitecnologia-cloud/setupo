"""Plugin routes — Admin catalog management + user install/uninstall.

Admin routes (require admin auth):
  POST   /catalog          — Publish a plugin to the catalog
  PATCH  /catalog/{id}     — Update a catalog entry
  DELETE /catalog/{id}     — Remove from catalog
  GET    /catalog          — List all catalog entries (including unpublished)

User routes (require project scope):
  GET    /                 — List available plugins + installation status
  POST   /install          — Install a plugin
  PATCH  /{plugin_id}      — Enable/disable, update config
  DELETE /{plugin_id}      — Uninstall

Mounted at /api/projects/{project_id}/plugins
"""
import logging
import secrets as token_gen
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from core import db
from core.models import InstallPluginRequest, UpdatePluginRequest
from server.deps import require_project, require_admin

logger = logging.getLogger("setupo.routes.plugins")
router = APIRouter()

# ── Default catalog (seeded on first list if DB is empty) ──────

_DEFAULT_CATALOG = [
    {
        "plugin_id": "monitoring",
        "name": "Monitoring",
        "description": "System metrics, alerts, and uptime tracking",
        "version": "1.0.0",
        "category": "observability",
    },
    {
        "plugin_id": "backups",
        "name": "Backups",
        "description": "Automated snapshot and restore for workspaces",
        "version": "1.0.0",
        "category": "data",
    },
    {
        "plugin_id": "ci-cd",
        "name": "CI/CD",
        "description": "Build and deploy pipelines for your projects",
        "version": "0.9.0",
        "category": "devops",
    },
    {
        "plugin_id": "logs",
        "name": "Log Viewer",
        "description": "Centralized log aggregation and search",
        "version": "1.0.0",
        "category": "observability",
    },
    {
        "plugin_id": "dns",
        "name": "DNS Manager",
        "description": "Manage DNS records for your domains",
        "version": "1.0.0",
        "category": "networking",
    },
    {
        "plugin_id": "cron",
        "name": "Cron Jobs",
        "description": "Schedule and manage recurring tasks",
        "version": "1.0.0",
        "category": "automation",
    },
]


async def _ensure_catalog_seeded():
    """Seed the plugin_catalog table with defaults if empty."""
    existing = await db.fetch_all("plugin_catalog")
    if existing:
        return
    now = datetime.utcnow().isoformat()
    for entry in _DEFAULT_CATALOG:
        await db.insert("plugin_catalog", {
            "id": f"cat_{token_gen.token_hex(8)}",
            "plugin_id": entry["plugin_id"],
            "name": entry["name"],
            "description": entry["description"],
            "version": entry["version"],
            "category": entry["category"],
            "icon": "",
            "author": "setupo",
            "published": True,
            "config_schema": {},
            "created_at": now,
            "updated_at": now,
        })
    logger.info("Seeded plugin catalog with %d default entries", len(_DEFAULT_CATALOG))


# ══════════════════════════════════════════════════════════════════
# ADMIN — Catalog management
# ══════════════════════════════════════════════════════════════════

@router.get("/catalog")
async def list_catalog(auth=Depends(require_admin)):
    """List all catalog entries (admin view — includes unpublished)."""
    entries = await db.fetch_all("plugin_catalog", order_by="created_at ASC")
    return {"catalog": entries}


@router.post("/catalog")
async def publish_plugin(
    entry: dict,
    auth=Depends(require_admin),
):
    """Publish a new plugin to the catalog."""
    plugin_id = entry.get("plugin_id", "").strip().lower()
    name = entry.get("name", "").strip()
    if not plugin_id or not name:
        raise HTTPException(400, "plugin_id and name are required")

    existing = await db.fetch_one("plugin_catalog", plugin_id=plugin_id)
    if existing:
        raise HTTPException(409, f"Plugin '{plugin_id}' already exists in catalog")

    now = datetime.utcnow().isoformat()
    data = {
        "id": f"cat_{token_gen.token_hex(8)}",
        "plugin_id": plugin_id,
        "name": name,
        "description": entry.get("description", ""),
        "version": entry.get("version", "1.0.0"),
        "category": entry.get("category", ""),
        "icon": entry.get("icon", ""),
        "author": entry.get("author", "setupo"),
        "published": entry.get("published", True),
        "config_schema": entry.get("config_schema", {}),
        "created_at": now,
        "updated_at": now,
    }
    await db.insert("plugin_catalog", data)
    logger.info("Published plugin %s to catalog", plugin_id)
    return {"ok": True, "entry": data}


@router.patch("/catalog/{plugin_id}")
async def update_catalog_entry(
    plugin_id: str,
    updates: dict,
    auth=Depends(require_admin),
):
    """Update a catalog entry (name, description, version, published, etc.)."""
    existing = await db.fetch_one("plugin_catalog", plugin_id=plugin_id)
    if not existing:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found in catalog")

    allowed = {"name", "description", "version", "category", "icon", "author", "published", "config_schema"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, f"No valid fields to update. Allowed: {', '.join(allowed)}")

    filtered["updated_at"] = datetime.utcnow().isoformat()
    await db.update("plugin_catalog", existing["id"], filtered)
    return {"ok": True, "plugin_id": plugin_id, "updated": list(filtered.keys())}


@router.delete("/catalog/{plugin_id}")
async def remove_from_catalog(
    plugin_id: str,
    auth=Depends(require_admin),
):
    """Remove a plugin from the catalog."""
    existing = await db.fetch_one("plugin_catalog", plugin_id=plugin_id)
    if not existing:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found in catalog")

    await db.delete("plugin_catalog", existing["id"])
    logger.info("Removed plugin %s from catalog", plugin_id)
    return {"ok": True, "plugin_id": plugin_id}


# ══════════════════════════════════════════════════════════════════
# USER — List, install, update, uninstall
# ══════════════════════════════════════════════════════════════════

@router.get("")
async def list_plugins(project_id: str = Depends(require_project)):
    """List published plugins with installation status for this project."""
    await _ensure_catalog_seeded()

    catalog = await db.fetch_all("plugin_catalog", order_by="created_at ASC", published=True)
    installed = await db.fetch_all("plugins", project_id=project_id)
    installed_map = {p["plugin_id"]: p for p in installed}

    plugins = []
    for entry in catalog:
        inst = installed_map.get(entry["plugin_id"])
        plugins.append({
            "plugin_id": entry["plugin_id"],
            "name": entry["name"],
            "description": entry["description"],
            "version": entry["version"],
            "category": entry["category"],
            "icon": entry.get("icon", ""),
            "author": entry.get("author", "setupo"),
            "installed": inst is not None,
            "enabled": inst["enabled"] if inst else False,
            "config": inst.get("config", {}) if inst else {},
            "installed_at": inst["installed_at"] if inst else None,
            "id": inst["id"] if inst else None,
        })

    return {"plugins": plugins}


@router.post("/install")
async def install_plugin(req: InstallPluginRequest, project_id: str = Depends(require_project)):
    """Install a plugin for this project."""
    await _ensure_catalog_seeded()

    catalog_entry = await db.fetch_one("plugin_catalog", plugin_id=req.plugin_id, published=True)
    if not catalog_entry:
        raise HTTPException(404, f"Plugin '{req.plugin_id}' not found in catalog")

    existing = await db.fetch_one("plugins", project_id=project_id, plugin_id=req.plugin_id)
    if existing:
        raise HTTPException(409, f"Plugin '{req.plugin_id}' is already installed")

    plugin_data = {
        "id": f"plg_{token_gen.token_hex(8)}",
        "project_id": project_id,
        "plugin_id": req.plugin_id,
        "name": catalog_entry["name"],
        "description": catalog_entry["description"],
        "version": catalog_entry["version"],
        "category": catalog_entry["category"],
        "enabled": True,
        "config": req.config,
        "installed_at": datetime.utcnow().isoformat(),
    }
    await db.insert("plugins", plugin_data)

    logger.info("Installed plugin %s for project %s", req.plugin_id, project_id)

    return {
        "ok": True,
        "plugin": {**plugin_data, "installed": True},
    }


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


@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str, project_id: str = Depends(require_project)):
    """Uninstall a plugin from this project."""
    existing = await db.fetch_one("plugins", project_id=project_id, plugin_id=plugin_id)
    if not existing:
        raise HTTPException(404, f"Plugin '{plugin_id}' is not installed")

    await db.delete("plugins", existing["id"])

    logger.info("Uninstalled plugin %s from project %s", plugin_id, project_id)

    return {"ok": True, "plugin_id": plugin_id}
