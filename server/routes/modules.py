import hashlib
import logging
import secrets as stdlib_secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from core import db
from core.zar.storage import R2Client
from server.config import settings
from server.deps import require_admin, get_auth
from server.auth.middleware import AuthContext

logger = logging.getLogger("setupo.routes.modules")
router = APIRouter()

MODULE_R2_PREFIX = "_modules"
MAX_UPLOAD_SIZE = 100 * 1024 * 1024


class PublishModuleRequest(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: str = "core"


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


def _get_r2() -> R2Client:
    cfg = settings.r2_config()
    if not cfg.endpoint:
        raise HTTPException(503, "R2 not configured")
    return R2Client(cfg)


def _module_r2_key(name: str, version: str) -> str:
    return f"{MODULE_R2_PREFIX}/{name}/v{version}.zar"


def _module_latest_key(name: str) -> str:
    return f"{MODULE_R2_PREFIX}/{name}/latest.zar"


async def _ensure_modules_seeded():
    existing = await db.fetch_all("modules")
    if existing:
        return
    now = datetime.now(timezone.utc).isoformat()
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
    logger.info("Seeded %d default modules", len(_DEFAULT_MODULES))


@router.get("/catalog")
async def list_catalog():
    await _ensure_modules_seeded()
    modules = await db.fetch_all("modules", order_by="name ASC", published=True)
    return {"modules": modules, "count": len(modules)}


@router.get("/catalog/{name}")
async def get_module(name: str):
    mod = await db.fetch_one("modules", name=name)
    if not mod or not mod.get("published"):
        raise HTTPException(404, f"Module '{name}' not found")
    return {"module": mod}


@router.get("")
async def list_all_modules(auth: AuthContext = Depends(require_admin)):
    await _ensure_modules_seeded()
    modules = await db.fetch_all("modules", order_by="name ASC")
    return {"modules": modules, "count": len(modules)}


@router.post("")
async def publish_module(req: PublishModuleRequest, auth: AuthContext = Depends(require_admin)):
    name = req.name.strip().lower()
    if not name:
        raise HTTPException(400, "Module name is required")

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.fetch_one("modules", name=name)

    if existing:
        updates = {
            "version": req.version,
            "description": req.description or existing["description"],
            "display_name": req.display_name or existing["display_name"],
            "category": req.category or existing["category"],
            "published": True,
            "updated_at": now,
        }
        await db.update("modules", existing["id"], updates)
        logger.info("Updated module %s to v%s", name, req.version)
        return {"ok": True, "action": "updated", "name": name, "version": req.version}

    mod_id = f"mod_{stdlib_secrets.token_hex(8)}"
    await db.insert("modules", {
        "id": mod_id,
        "name": name,
        "display_name": req.display_name or name,
        "description": req.description,
        "version": req.version,
        "category": req.category,
        "r2_key": "",
        "size": 0,
        "hash": "",
        "published": True,
        "created_at": now,
        "updated_at": now,
    })
    logger.info("Published new module %s v%s", name, req.version)
    return {"ok": True, "action": "created", "name": name, "version": req.version}


@router.post("/{name}/upload")
async def upload_module_zar(
    name: str,
    version: str = Form(""),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_admin),
):
    mod = await db.fetch_one("modules", name=name)
    if not mod:
        raise HTTPException(404, f"Module '{name}' not found")

    zar_bytes = await file.read()
    if len(zar_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"File too large (max {MAX_UPLOAD_SIZE // (1024 * 1024)}MB)")
    if len(zar_bytes) == 0:
        raise HTTPException(400, "Empty file")

    upload_version = version or mod["version"]
    content_hash = hashlib.sha256(zar_bytes).hexdigest()
    versioned_key = _module_r2_key(name, upload_version)
    latest_key = _module_latest_key(name)

    r2 = _get_r2()
    try:
        ok = await r2.upload(versioned_key, zar_bytes)
        if not ok:
            raise HTTPException(502, f"R2 upload failed for {versioned_key}")
        await r2.upload(latest_key, zar_bytes)
    finally:
        await r2.close()

    now = datetime.now(timezone.utc).isoformat()
    await db.update("modules", mod["id"], {
        "r2_key": versioned_key,
        "size": len(zar_bytes),
        "hash": f"sha256:{content_hash}",
        "version": upload_version,
        "updated_at": now,
    })

    logger.info("Uploaded module %s v%s (%d bytes) to R2", name, upload_version, len(zar_bytes))
    return {
        "ok": True,
        "name": name,
        "version": upload_version,
        "r2_key": versioned_key,
        "size": len(zar_bytes),
        "hash": f"sha256:{content_hash}",
    }


@router.get("/{name}/versions")
async def list_module_versions(name: str):
    mod = await db.fetch_one("modules", name=name)
    if not mod:
        raise HTTPException(404, f"Module '{name}' not found")

    r2 = _get_r2()
    try:
        prefix = f"{MODULE_R2_PREFIX}/{name}/v"
        keys = await r2.list_keys(prefix)
    finally:
        await r2.close()

    versions = []
    for k in keys:
        filename = k.rsplit("/", 1)[-1]
        if filename.startswith("v") and filename.endswith(".zar"):
            versions.append(filename[1:-4])

    return {
        "name": name,
        "versions": sorted(versions),
        "current": mod["version"],
        "r2_key": mod.get("r2_key", ""),
    }


@router.get("/{name}/download")
async def download_module_info(name: str, version: str = ""):
    mod = await db.fetch_one("modules", name=name)
    if not mod or not mod.get("published"):
        raise HTTPException(404, f"Module '{name}' not found")

    if version:
        r2_key = _module_r2_key(name, version)
    elif mod.get("r2_key"):
        r2_key = mod["r2_key"]
    else:
        r2_key = _module_latest_key(name)

    r2 = _get_r2()
    try:
        exists = await r2.exists(r2_key)
    finally:
        await r2.close()

    if not exists:
        raise HTTPException(404, f"No .zar package found for {name} (key: {r2_key})")

    return {
        "name": name,
        "version": version or mod["version"],
        "r2_key": r2_key,
        "size": mod.get("size", 0),
        "hash": mod.get("hash", ""),
    }


@router.patch("/{name}")
async def update_module(name: str, updates: dict, auth: AuthContext = Depends(require_admin)):
    existing = await db.fetch_one("modules", name=name)
    if not existing:
        raise HTTPException(404, f"Module '{name}' not found")

    allowed = {"display_name", "description", "version", "category", "published"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(400, f"No valid fields. Allowed: {', '.join(sorted(allowed))}")

    filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.update("modules", existing["id"], filtered)
    return {"ok": True, "name": name, "updated": list(filtered.keys())}


@router.delete("/{name}")
async def remove_module(name: str, auth: AuthContext = Depends(require_admin)):
    existing = await db.fetch_one("modules", name=name)
    if not existing:
        raise HTTPException(404, f"Module '{name}' not found")

    await db.delete("modules", existing["id"])
    logger.info("Removed module %s", name)
    return {"ok": True, "name": name}
