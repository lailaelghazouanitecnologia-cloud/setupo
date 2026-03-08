"""NSO Addons — Catalog & installation management for connectors, plugins, and marketplace."""

import logging
import secrets as token_gen
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from nso.shared import db
from nso.shared.models import InstallPluginRequest, UpdatePluginRequest
from nso.engine.addons.service import (
    ADDON_TYPES, DEFAULT_CONNECTORS, DEFAULT_PLUGINS, DEFAULT_MARKETPLACE,
)
from nso.shared.deps import require_project, require_admin

logger = logging.getLogger("nso.routes.addons")
router = APIRouter()


async def _ensure_catalog_seeded():
    """Seed default catalog entries and remove stale ones."""
    existing = await db.fetch_all("addon_catalog")

    all_defaults = (
        [(e, "connector") for e in DEFAULT_CONNECTORS]
        + [(e, "plugin") for e in DEFAULT_PLUGINS]
        + [(e, "marketplace") for e in DEFAULT_MARKETPLACE]
    )
    valid_keys = {(e["addon_id"], t) for e, t in all_defaults}

    existing_keys = {(e["addon_id"], e["addon_type"]) for e in existing}

    # Remove catalog entries that are no longer in defaults
    for entry in existing:
        key = (entry["addon_id"], entry["addon_type"])
        if key not in valid_keys and entry.get("author") == "nso":
            await db.delete("addon_catalog", entry["id"])
            logger.info("Removed stale catalog entry: %s (%s)", entry["addon_id"], entry["addon_type"])

    # Add missing catalog entries
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for entry, addon_type in all_defaults:
        key = (entry["addon_id"], addon_type)
        if key not in existing_keys:
            await db.insert("addon_catalog", {
                "id": f"cat_{token_gen.token_hex(8)}",
                "addon_id": entry["addon_id"],
                "addon_type": addon_type,
                "name": entry["name"],
                "description": entry["description"],
                "version": "1.0.0",
                "category": entry.get("category", ""),
                "icon": entry.get("icon", ""),
                "author": entry.get("author", "nso"),
                "published": True,
                "config_schema": entry.get("config_schema", {}),
                "created_at": now,
                "updated_at": now,
            })
            added += 1

    if added:
        logger.info("Seeded %d new addon catalog entries", added)


# Also keep old plugin_catalog seeded for backwards compat during migration
async def _ensure_legacy_seeded():
    existing = await db.fetch_all("plugin_catalog")
    if existing:
        return

    now = datetime.now(timezone.utc).isoformat()
    for entry in DEFAULT_PLUGINS:
        await db.insert("plugin_catalog", {
            "id": f"cat_{token_gen.token_hex(8)}",
            "plugin_id": entry["addon_id"],
            "name": entry["name"],
            "description": entry["description"],
            "version": "1.0.0",
            "category": entry.get("category", ""),
            "icon": entry.get("icon", ""),
            "author": "nso",
            "published": True,
            "config_schema": entry.get("config_schema", {}),
            "created_at": now,
            "updated_at": now,
        })


from nso.shared.secrets import CONNECTOR_SECRET_MAP, classify_secret


async def _sync_connector_secrets(project_id: str, connector_id: str, config: dict):
    """Sync connector credentials to project_secrets for visibility in Secrets panel."""
    key_map = CONNECTOR_SECRET_MAP.get(connector_id, {})
    if not key_map:
        return

    scope = "general"
    now = datetime.now(timezone.utc).isoformat()

    for config_field, secret_key in key_map.items():
        value = config.get(config_field, "")
        if not value:
            continue

        bucket = classify_secret(secret_key)
        existing = await db.fetch_one("project_secrets", project_id=project_id, key=secret_key, scope=scope)
        if existing:
            conn = await db.get_db()
            await conn.execute(
                "UPDATE project_secrets SET value = ?, bucket = ?, updated_at = ? WHERE id = ?",
                (value, bucket, now, existing["id"]),
            )
            await conn.commit()
        else:
            await db.insert("project_secrets", {
                "id": f"sec_{uuid.uuid4().hex[:16]}",
                "project_id": project_id,
                "key": secret_key,
                "value": value,
                "bucket": bucket,
                "scope": scope,
            })

    logger.info("Synced %s connector secrets for project %s", connector_id, project_id)


# ═══════════════════════════════════════════
#  CATALOG (admin)
# ═══════════════════════════════════════════

@router.get("/catalog")
async def list_catalog(addon_type: str = "", auth=Depends(require_admin)):
    """List catalog entries. Optionally filter by addon_type (connector, plugin, marketplace)."""
    await _ensure_catalog_seeded()
    if addon_type and addon_type in ADDON_TYPES:
        entries = await db.fetch_all("addon_catalog", order_by="created_at ASC", addon_type=addon_type)
    else:
        entries = await db.fetch_all("addon_catalog", order_by="created_at ASC")
    return {"catalog": entries}


@router.post("/catalog")
async def publish_addon(entry: dict, auth=Depends(require_admin)):
    """Publish a new addon to the catalog."""
    addon_id = entry.get("addon_id", "").strip().lower()
    addon_type = entry.get("addon_type", "plugin").strip().lower()
    name = entry.get("name", "").strip()

    if not addon_id or not name:
        raise HTTPException(400, "addon_id and name are required")
    if addon_type not in ADDON_TYPES:
        raise HTTPException(400, f"addon_type must be one of: {', '.join(ADDON_TYPES)}")

    existing = await db.fetch_one("addon_catalog", addon_id=addon_id, addon_type=addon_type)
    if existing:
        raise HTTPException(409, f"Addon '{addon_id}' ({addon_type}) already exists in catalog")

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": f"cat_{token_gen.token_hex(8)}",
        "addon_id": addon_id,
        "addon_type": addon_type,
        "name": name,
        "description": entry.get("description", ""),
        "version": entry.get("version", "1.0.0"),
        "category": entry.get("category", ""),
        "icon": entry.get("icon", ""),
        "author": entry.get("author", "nso"),
        "published": entry.get("published", True),
        "config_schema": entry.get("config_schema", {}),
        "created_at": now,
        "updated_at": now,
    }
    await db.insert("addon_catalog", data)
    logger.info("Published %s addon %s to catalog", addon_type, addon_id)
    return {"ok": True, "entry": data}


@router.patch("/catalog/{addon_type}/{addon_id}")
async def update_catalog_entry(addon_type: str, addon_id: str, updates: dict, auth=Depends(require_admin)):
    """Update a catalog entry."""
    if addon_type not in ADDON_TYPES:
        raise HTTPException(400, f"Invalid addon_type: {addon_type}")

    existing = await db.fetch_one("addon_catalog", addon_id=addon_id, addon_type=addon_type)
    if not existing:
        raise HTTPException(404, f"Addon '{addon_id}' ({addon_type}) not found in catalog")

    allowed = {"name", "description", "version", "category", "icon", "author", "published", "config_schema"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, f"No valid fields. Allowed: {', '.join(sorted(allowed))}")

    filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.update("addon_catalog", existing["id"], filtered)
    return {"ok": True, "addon_id": addon_id, "addon_type": addon_type, "updated": list(filtered.keys())}


@router.delete("/catalog/{addon_type}/{addon_id}")
async def remove_from_catalog(addon_type: str, addon_id: str, auth=Depends(require_admin)):
    """Remove an addon from the catalog."""
    if addon_type not in ADDON_TYPES:
        raise HTTPException(400, f"Invalid addon_type: {addon_type}")

    existing = await db.fetch_one("addon_catalog", addon_id=addon_id, addon_type=addon_type)
    if not existing:
        raise HTTPException(404, f"Addon '{addon_id}' ({addon_type}) not found in catalog")

    await db.delete("addon_catalog", existing["id"])
    logger.info("Removed %s addon %s from catalog", addon_type, addon_id)
    return {"ok": True, "addon_id": addon_id, "addon_type": addon_type}


# ═══════════════════════════════════════════
#  ADDONS (per-project install/manage)
# ═══════════════════════════════════════════

@router.get("")
async def list_addons(addon_type: str = "", project_id: str = Depends(require_project)):
    """List addons for a project, combining catalog + install status."""
    await _ensure_catalog_seeded()

    if addon_type and addon_type in ADDON_TYPES:
        catalog = await db.fetch_all("addon_catalog", order_by="created_at ASC", published=True, addon_type=addon_type)
    else:
        catalog = await db.fetch_all("addon_catalog", order_by="created_at ASC", published=True)

    installed = await db.fetch_all("addons", order_by="installed_at DESC", project_id=project_id)
    installed_map = {(a["addon_id"], a["addon_type"]): a for a in installed}

    addons = []
    for entry in catalog:
        key = (entry["addon_id"], entry["addon_type"])
        inst = installed_map.get(key)
        addons.append({
            "addon_id": entry["addon_id"],
            "addon_type": entry["addon_type"],
            "name": entry["name"],
            "description": entry["description"],
            "version": entry["version"],
            "category": entry["category"],
            "icon": entry.get("icon", ""),
            "author": entry.get("author", "nso"),
            "installed": inst is not None,
            "enabled": inst["enabled"] if inst else False,
            "config": inst.get("config", {}) if inst else {},
            "installed_at": inst["installed_at"] if inst else None,
            "id": inst["id"] if inst else None,
        })

    return {"addons": addons}


@router.post("/install")
async def install_addon(req: InstallPluginRequest, addon_type: str = "plugin", project_id: str = Depends(require_project)):
    """Install an addon from the catalog."""
    await _ensure_catalog_seeded()

    if addon_type not in ADDON_TYPES:
        addon_type = "plugin"

    catalog_entry = await db.fetch_one("addon_catalog", addon_id=req.plugin_id, addon_type=addon_type, published=True)
    if not catalog_entry:
        # Fallback: try any type
        d = await db.get_db()
        cursor = await d.execute(
            "SELECT * FROM addon_catalog WHERE addon_id = ? AND published = 1 LIMIT 1",
            [req.plugin_id],
        )
        row = await cursor.fetchone()
        if row:
            catalog_entry = dict(row)
        else:
            raise HTTPException(404, f"Addon '{req.plugin_id}' not found in catalog")

    existing = await db.fetch_one("addons", project_id=project_id, addon_id=req.plugin_id, addon_type=catalog_entry["addon_type"])
    if existing:
        raise HTTPException(409, f"Addon '{req.plugin_id}' is already installed")

    addon_data = {
        "id": f"adn_{token_gen.token_hex(8)}",
        "project_id": project_id,
        "addon_id": req.plugin_id,
        "addon_type": catalog_entry["addon_type"],
        "name": catalog_entry["name"],
        "description": catalog_entry["description"],
        "version": catalog_entry["version"],
        "category": catalog_entry["category"],
        "enabled": True,
        "config": req.config,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("addons", addon_data)

    # Also insert into legacy plugins table for backwards compat
    if catalog_entry["addon_type"] == "plugin":
        await _ensure_legacy_seeded()
        try:
            await db.insert("plugins", {
                "id": f"plg_{token_gen.token_hex(8)}",
                "project_id": project_id,
                "plugin_id": req.plugin_id,
                "name": catalog_entry["name"],
                "description": catalog_entry["description"],
                "version": catalog_entry["version"],
                "category": catalog_entry["category"],
                "enabled": True,
                "config": req.config,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass  # Legacy table may not be in sync

    # Sync connector credentials to project_secrets
    if catalog_entry["addon_type"] == "connector" and req.config:
        await _sync_connector_secrets(project_id, req.plugin_id, req.config)

    logger.info("Installed %s addon %s for project %s", catalog_entry["addon_type"], req.plugin_id, project_id)
    return {"ok": True, "addon": {**addon_data, "installed": True}}


@router.patch("/{addon_id}")
async def update_addon(addon_id: str, req: UpdatePluginRequest, addon_type: str = "", project_id: str = Depends(require_project)):
    """Update an installed addon (enable/disable, config)."""
    if addon_type and addon_type in ADDON_TYPES:
        existing = await db.fetch_one("addons", project_id=project_id, addon_id=addon_id, addon_type=addon_type)
    else:
        existing = await db.fetch_one("addons", project_id=project_id, addon_id=addon_id)

    if not existing:
        raise HTTPException(404, f"Addon '{addon_id}' is not installed")

    updates = {}
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    if req.config is not None:
        updates["config"] = req.config

    if updates:
        await db.update("addons", existing["id"], updates)

        # Sync connector credentials to project_secrets
        if existing.get("addon_type") == "connector" and req.config is not None:
            await _sync_connector_secrets(project_id, addon_id, req.config)

        # Sync to legacy plugins table
        if existing.get("addon_type") == "plugin":
            legacy = await db.fetch_one("plugins", project_id=project_id, plugin_id=addon_id)
            if legacy:
                try:
                    await db.update("plugins", legacy["id"], updates)
                except Exception:
                    pass

    return {"ok": True, "addon_id": addon_id, "updated": list(updates.keys())}


@router.delete("/{addon_id}")
async def uninstall_addon(addon_id: str, addon_type: str = "", project_id: str = Depends(require_project)):
    """Uninstall an addon."""
    if addon_type and addon_type in ADDON_TYPES:
        existing = await db.fetch_one("addons", project_id=project_id, addon_id=addon_id, addon_type=addon_type)
    else:
        existing = await db.fetch_one("addons", project_id=project_id, addon_id=addon_id)

    if not existing:
        raise HTTPException(404, f"Addon '{addon_id}' is not installed")

    await db.delete("addons", existing["id"])

    # Remove from legacy plugins table too
    if existing.get("addon_type") == "plugin":
        legacy = await db.fetch_one("plugins", project_id=project_id, plugin_id=addon_id)
        if legacy:
            try:
                await db.delete("plugins", legacy["id"])
            except Exception:
                pass

    logger.info("Uninstalled addon %s from project %s", addon_id, project_id)
    return {"ok": True, "addon_id": addon_id}
