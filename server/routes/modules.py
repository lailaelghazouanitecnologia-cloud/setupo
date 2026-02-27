"""Modules routes — .zar marketplace for platform modules.

Admin (ayman_gha@hotmail.com) controls the marketplace:
  POST   /               — Publish/update a module
  DELETE /{name}          — Remove a module
  GET    /                — List all modules (admin sees unpublished too)

Users can browse:
  GET    /catalog         — List published modules
  GET    /{name}          — Get module details + download info

Modules are the platform's own components (server, core, dashboard, nso-agent)
packaged as .zar files and stored in R2. Admin publishes updates, instances pull them.

Mounted at /api/modules
"""
import logging
import secrets as stdlib_secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db
from server.deps import require_admin, get_auth
from server.auth.middleware import AuthContext

logger = logging.getLogger("setupo.routes.modules")
router = APIRouter()


class PublishModuleRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: str = "core"
    r2_key: str = ""
    size: int = 0
    hash: str = ""


class ModuleOut(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    version: str
    category: str
    r2_key: str
    size: int
    hash: str
    published: bool
    created_at: str
    updated_at: str


# ── Default modules (seeded on first list) ─────────────────

_DEFAULT_MODULES = [
    {
        "name": "server",
        "display_name": "API Server",
        "description": "FastAPI backend — routes, auth, config",
        "category": "core",
    },
    {
        "name": "core",
        "display_name": "Core Library",
        "description": "Business logic — DB, models, providers, zar packer",
        "category": "core",
    },
    {
        "name": "nso-agent",
        "display_name": "NSO Agent",
        "description": "VPS management agent — files, exec, deploy, secrets",
        "category": "core",
    },
    {
        "name": "dashboard",
        "display_name": "Dashboard",
        "description": "Next.js admin dashboard — static build",
        "category": "frontend",
    },
]


async def _ensure_modules_seeded():
    """Seed modules table with defaults if empty."""
    existing = await db.fetch_all("modules")
    if existing:
        return
    now = datetime.utcnow().isoformat()
    for mod in _DEFAULT_MODULES:
        await db.insert("modules", {
            "id": f"mod_{stdlib_secrets.token_hex(8)}",
            "name": mod["name"],
            "display_name": mod["display_name"],
            "description": mod["description"],
            "version": "0.1.0",
            "category": mod["category"],
            "r2_key": "",
            "size": 0,
            "hash": "",
            "published": True,
            "created_at": now,
            "updated_at": now,
        })
    logger.info("Seeded modules with %d defaults", len(_DEFAULT_MODULES))


# ── Public: browse catalog ──────────────────────────────────

@router.get("/catalog")
async def list_catalog():
    """List published modules (public)."""
    await _ensure_modules_seeded()
    modules = await db.fetch_all("modules", order_by="name ASC", published=True)
    return {"modules": modules, "count": len(modules)}


@router.get("/catalog/{name}")
async def get_module(name: str):
    """Get module details."""
    mod = await db.fetch_one("modules", name=name)
    if not mod or not mod.get("published"):
        raise HTTPException(404, f"Module '{name}' not found")
    return {"module": mod}


# ── Admin: manage modules ───────────────────────────────────

@router.get("")
async def list_all_modules(auth: AuthContext = Depends(require_admin)):
    """List all modules including unpublished (admin only)."""
    await _ensure_modules_seeded()
    modules = await db.fetch_all("modules", order_by="name ASC")
    return {"modules": modules, "count": len(modules)}


@router.post("")
async def publish_module(req: PublishModuleRequest, auth: AuthContext = Depends(require_admin)):
    """Publish or update a module in the marketplace."""
    name = req.name.strip().lower()
    if not name:
        raise HTTPException(400, "Module name is required")

    now = datetime.utcnow().isoformat()
    existing = await db.fetch_one("modules", name=name)

    if existing:
        # Update existing module
        updates = {
            "version": req.version,
            "description": req.description or existing["description"],
            "display_name": req.display_name or existing["display_name"],
            "category": req.category or existing["category"],
            "r2_key": req.r2_key or existing["r2_key"],
            "size": req.size or existing["size"],
            "hash": req.hash or existing["hash"],
            "published": True,
            "updated_at": now,
        }
        await db.update("modules", existing["id"], updates)
        logger.info("Updated module %s to v%s", name, req.version)
        return {"ok": True, "action": "updated", "name": name, "version": req.version}
    else:
        # Create new module
        mod_id = f"mod_{stdlib_secrets.token_hex(8)}"
        await db.insert("modules", {
            "id": mod_id,
            "name": name,
            "display_name": req.display_name or name,
            "description": req.description,
            "version": req.version,
            "category": req.category,
            "r2_key": req.r2_key,
            "size": req.size,
            "hash": req.hash,
            "published": True,
            "created_at": now,
            "updated_at": now,
        })
        logger.info("Published new module %s v%s", name, req.version)
        return {"ok": True, "action": "created", "name": name, "version": req.version}


@router.patch("/{name}")
async def update_module(name: str, updates: dict, auth: AuthContext = Depends(require_admin)):
    """Update module metadata."""
    existing = await db.fetch_one("modules", name=name)
    if not existing:
        raise HTTPException(404, f"Module '{name}' not found")

    allowed = {"display_name", "description", "version", "category", "r2_key", "size", "hash", "published"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, f"No valid fields. Allowed: {', '.join(allowed)}")

    filtered["updated_at"] = datetime.utcnow().isoformat()
    await db.update("modules", existing["id"], filtered)
    return {"ok": True, "name": name, "updated": list(filtered.keys())}


@router.delete("/{name}")
async def remove_module(name: str, auth: AuthContext = Depends(require_admin)):
    """Remove a module from the marketplace."""
    existing = await db.fetch_one("modules", name=name)
    if not existing:
        raise HTTPException(404, f"Module '{name}' not found")

    await db.delete("modules", existing["id"])
    logger.info("Removed module %s", name)
    return {"ok": True, "name": name}
