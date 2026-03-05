"""NSO AI Apps — API routes for AI-powered services.

Two access paths:
1. Admin: publish/manage AI apps in the catalog
2. Projects: browse + run AI apps via API key (from deployed apps or dashboard)

Usage from a deployed app:
    POST https://nso.dev/api/projects/{pid}/ai/apps/{slug}/run
    Authorization: Bearer sk_live_xxx
    Content-Type: application/json
    {"prompt": "Generate a logo for a coffee shop", "style": "minimal"}
"""

import json
import logging
import re
import secrets as token_gen
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_admin, require_project, require_user
from nso.engine.addons.ai_apps_service import (
    call_baseten_model,
    validate_input,
    build_baseten_payload,
    gather_memory,
    save_memory,
    store_output_to_r2,
)

logger = logging.getLogger("nso.ai_apps.routes")

# ═══════════════════════════════════════════════════════════════
#  ADMIN ROUTER — manage AI app catalog
# ═══════════════════════════════════════════════════════════════
admin_router = APIRouter()


class CreateAIAppRequest(BaseModel):
    name: str
    slug: str = ""  # auto-generated from name if empty
    description: str = ""
    long_description: str = ""
    category: str = "general"
    icon: str = "cpu"
    cover_image: str = ""
    pricing: str = "free"
    credits_per_run: int = 0
    baseten_model_id: str = ""
    baseten_api_url: str = ""
    baseten_api_key: str = ""
    input_schema: dict = {}
    output_schema: dict = {}
    example_input: dict = {}
    example_output: dict = {}
    system_prompt: str = ""
    max_timeout_seconds: int = 60
    published: bool = False
    featured: bool = False


class UpdateAIAppRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    long_description: str | None = None
    category: str | None = None
    icon: str | None = None
    cover_image: str | None = None
    pricing: str | None = None
    credits_per_run: int | None = None
    baseten_model_id: str | None = None
    baseten_api_url: str | None = None
    baseten_api_key: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    example_input: dict | None = None
    example_output: dict | None = None
    system_prompt: str | None = None
    max_timeout_seconds: int | None = None
    published: bool | None = None
    featured: bool | None = None


def _slugify(name: str) -> str:
    """Generate URL-safe slug from name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


@admin_router.get("")
async def admin_list_ai_apps(_admin=Depends(require_admin)):
    """List all AI apps (including unpublished)."""
    apps = await db.fetch_all("ai_apps", order_by="created_at DESC")
    return {"apps": apps, "count": len(apps)}


@admin_router.post("")
async def admin_create_ai_app(req: CreateAIAppRequest, _admin=Depends(require_admin)):
    """Publish a new AI app to the catalog."""
    slug = req.slug or _slugify(req.name)
    if not slug:
        raise HTTPException(400, "Could not generate slug from name")

    # Check uniqueness
    existing = await db.fetch_one("ai_apps", slug=slug)
    if existing:
        raise HTTPException(409, f"AI app with slug '{slug}' already exists")

    app_id = f"aiapp_{token_gen.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "id": app_id,
        "name": req.name,
        "slug": slug,
        "description": req.description,
        "long_description": req.long_description,
        "category": req.category,
        "icon": req.icon,
        "cover_image": req.cover_image,
        "author": "nso",
        "published": req.published,
        "featured": req.featured,
        "pricing": req.pricing,
        "credits_per_run": req.credits_per_run,
        "baseten_model_id": req.baseten_model_id,
        "baseten_api_url": req.baseten_api_url,
        "baseten_api_key": req.baseten_api_key,
        "input_schema": req.input_schema,
        "output_schema": req.output_schema,
        "example_input": req.example_input,
        "example_output": req.example_output,
        "system_prompt": req.system_prompt,
        "max_timeout_seconds": req.max_timeout_seconds,
        "total_runs": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.insert("ai_apps", data)

    return {"ok": True, "app": data}


@admin_router.get("/{app_id}")
async def admin_get_ai_app(app_id: str, _admin=Depends(require_admin)):
    """Get full AI app details (including secrets like API keys)."""
    app = await db.fetch_one("ai_apps", id=app_id)
    if not app:
        app = await db.fetch_one("ai_apps", slug=app_id)
    if not app:
        raise HTTPException(404, "AI app not found")

    # Get run stats
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success, "
        "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors, "
        "AVG(latency_ms) as avg_latency "
        "FROM ai_app_runs WHERE app_id = ?",
        [app["id"]],
    )
    stats = dict(await cursor.fetchone())

    return {"app": app, "stats": stats}


@admin_router.patch("/{app_id}")
async def admin_update_ai_app(app_id: str, req: UpdateAIAppRequest, _admin=Depends(require_admin)):
    """Update an AI app."""
    app = await db.fetch_one("ai_apps", id=app_id)
    if not app:
        app = await db.fetch_one("ai_apps", slug=app_id)
    if not app:
        raise HTTPException(404, "AI app not found")

    updates = {}
    for field, value in req.model_dump(exclude_none=True).items():
        updates[field] = value
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.update("ai_apps", app["id"], updates)
    return {"ok": True, "updated": list(updates.keys())}


@admin_router.delete("/{app_id}")
async def admin_delete_ai_app(app_id: str, _admin=Depends(require_admin)):
    """Remove an AI app from the catalog."""
    app = await db.fetch_one("ai_apps", id=app_id)
    if not app:
        app = await db.fetch_one("ai_apps", slug=app_id)
    if not app:
        raise HTTPException(404, "AI app not found")

    # Delete runs too
    d = await db.get_db()
    await d.execute("DELETE FROM ai_app_runs WHERE app_id = ?", [app["id"]])
    await d.commit()
    await db.delete("ai_apps", app["id"])
    return {"ok": True}


@admin_router.post("/{app_id}/assets")
async def admin_upload_asset(
    app_id: str,
    file: UploadFile = File(...),
    asset_type: str = Form("cover"),  # cover, icon, preview
    _admin=Depends(require_admin),
):
    """Upload an asset file (icon, cover image, preview) for an AI app.

    Files are stored in R2 under: _ai_apps/{slug}/{asset_type}/{filename}
    The app's cover_image/icon field is updated with the R2 public URL.
    """
    app = await db.fetch_one("ai_apps", id=app_id)
    if not app:
        app = await db.fetch_one("ai_apps", slug=app_id)
    if not app:
        raise HTTPException(404, "AI app not found")

    if asset_type not in ("cover", "icon", "preview", "screenshot"):
        raise HTTPException(400, "asset_type must be one of: cover, icon, preview, screenshot")

    # Read file content
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(413, "File too large (max 10MB)")

    # Determine content type
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or f"{asset_type}.bin"

    # Upload to R2
    from nso.engine.storage.service import R2Client
    from nso.config import settings

    r2_cfg = settings.r2_config()
    r2_key = f"_ai_apps/{app['slug']}/{asset_type}/{filename}"

    async with R2Client(r2_cfg) as r2:
        ok = await r2.upload(r2_key, content, content_type)

    if not ok:
        raise HTTPException(502, "Failed to upload asset to R2")

    # Build public URL
    public_url = f"{r2_cfg.public_url}/{r2_key}" if r2_cfg.public_url else r2_key

    # Update the app field
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if asset_type == "cover":
        updates["cover_image"] = public_url
    elif asset_type == "icon":
        updates["icon"] = public_url

    await db.update("ai_apps", app["id"], updates)

    return {
        "ok": True,
        "asset_type": asset_type,
        "filename": filename,
        "r2_key": r2_key,
        "url": public_url,
        "size": len(content),
    }


@admin_router.get("/{app_id}/runs")
async def admin_list_runs(
    app_id: str,
    limit: int = Query(50, ge=1, le=500),
    _admin=Depends(require_admin),
):
    """List execution history for an AI app (admin view, all projects)."""
    app = await db.fetch_one("ai_apps", id=app_id)
    if not app:
        app = await db.fetch_one("ai_apps", slug=app_id)
    if not app:
        raise HTTPException(404, "AI app not found")

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM ai_app_runs WHERE app_id = ? ORDER BY created_at DESC LIMIT ?",
        [app["id"], limit],
    )
    runs = [dict(r) for r in await cursor.fetchall()]
    return {"runs": runs, "count": len(runs)}


# ═══════════════════════════════════════════════════════════════
#  PROJECT ROUTER — browse catalog + run apps (API key auth)
# ═══════════════════════════════════════════════════════════════
project_router = APIRouter()


@project_router.get("")
async def list_ai_apps(
    category: str = Query("", description="Filter by category"),
    featured: bool = Query(False, description="Only featured apps"),
    _project_id: str = Depends(require_project),
):
    """List published AI apps available to this project.

    Called from deployed apps or dashboard to discover available AI services.
    """
    d = await db.get_db()
    query = "SELECT id, name, slug, description, category, icon, cover_image, " \
            "pricing, credits_per_run, featured, input_schema, output_schema, " \
            "example_input, example_output, total_runs " \
            "FROM ai_apps WHERE published = 1"
    params: list = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if featured:
        query += " AND featured = 1"

    query += " ORDER BY featured DESC, total_runs DESC"
    cursor = await d.execute(query, params)
    apps = [dict(r) for r in await cursor.fetchall()]

    # Parse JSON fields
    for app in apps:
        for field in ("input_schema", "output_schema", "example_input", "example_output"):
            if isinstance(app.get(field), str):
                try:
                    app[field] = json.loads(app[field])
                except Exception:
                    pass

    return {"apps": apps, "count": len(apps)}


@project_router.get("/{slug}")
async def get_ai_app(slug: str, _project_id: str = Depends(require_project)):
    """Get AI app details + form schema.

    Returns everything needed to render the app's presentation and form in the dashboard,
    or to understand the API contract for calling from a deployed app.
    """
    app = await db.fetch_one("ai_apps", slug=slug, published=True)
    if not app:
        raise HTTPException(404, f"AI app '{slug}' not found or not published")

    # Don't expose internal fields
    safe_app = {k: v for k, v in app.items() if k not in (
        "baseten_model_id", "baseten_api_url", "baseten_api_key", "system_prompt",
    )}

    return {"app": safe_app}


@project_router.post("/{slug}/run")
async def run_ai_app(slug: str, request: Request, project_id: str = Depends(require_project)):
    """Execute an AI app.

    This is the main API endpoint that deployed apps call.

    Usage from deployed app code:
        import httpx
        resp = httpx.post(
            "https://nso.dev/api/projects/{pid}/ai/apps/image-generator/run",
            headers={"Authorization": "Bearer sk_live_xxx"},
            json={"prompt": "a sunset over mountains", "style": "watercolor"}
        )
        result = resp.json()
    """
    app = await db.fetch_one("ai_apps", slug=slug, published=True)
    if not app:
        raise HTTPException(404, f"AI app '{slug}' not found or not published")

    # Parse request body
    try:
        input_data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    if not isinstance(input_data, dict):
        raise HTTPException(400, "Body must be a JSON object")

    # Parse input_schema if it's a string
    input_schema = app.get("input_schema", {})
    if isinstance(input_schema, str):
        try:
            input_schema = json.loads(input_schema)
        except Exception:
            input_schema = {}

    # Validate input against schema
    if input_schema:
        errors = validate_input(input_data, input_schema)
        if errors:
            raise HTTPException(422, {"validation_errors": errors})

    # Create run record
    run_id = f"run_{token_gen.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()
    run_data = {
        "id": run_id,
        "app_id": app["id"],
        "project_id": project_id,
        "input": input_data,
        "status": "running",
        "created_at": now,
    }
    await db.insert("ai_app_runs", run_data)

    # Extract output folder preference (default: "assets")
    output_folder = input_data.pop("_output_folder", "assets")

    # Gather memory/context for the AI agent
    memory = await gather_memory(project_id, app["id"], db)

    # If user sent preferences, save them
    user_prefs = input_data.pop("_preferences", None)
    if user_prefs and isinstance(user_prefs, dict):
        await save_memory(project_id, app["id"], user_prefs, db)
        memory["preferences"].update(user_prefs)

    # Ensure output folder is in preferences
    if "output_folder" not in memory.get("preferences", {}):
        memory.setdefault("preferences", {})["output_folder"] = output_folder

    # Resolve instance to proxy the AI call through the user's agent
    instance_id = input_data.pop("_instance_id", "")
    from nso.engine.storage.routes import (
        _get_agent_url, _get_agent_token, _resolve_instance,
    )

    try:
        resolved_instance_id = await _resolve_instance("", project_id, instance_id)
    except HTTPException:
        # No instance found — fall back to direct call from central
        resolved_instance_id = ""

    system_prompt = app.get("system_prompt", "")
    if isinstance(system_prompt, str) and not system_prompt:
        system_prompt = ""
    timeout = app.get("max_timeout_seconds", 60) or 60

    if resolved_instance_id:
        # ── PROXY VIA AGENT (preferred) ──
        # Same backend that runs deploys — executes on user's VPS
        agent_url = await _get_agent_url(project_id, resolved_instance_id)
        agent_token = await _get_agent_token(agent_url)

        agent_payload = {
            "app_slug": slug,
            "run_id": run_id,
            "api_url": app.get("baseten_api_url", ""),
            "api_key": app.get("baseten_api_key", ""),
            "model_id": app.get("baseten_model_id", ""),
            "payload": input_data,
            "system_prompt": system_prompt,
            "memory": memory,
            "timeout": float(timeout),
            "output_folder": output_folder,
            "save_output": True,
        }

        try:
            async with httpx.AsyncClient(timeout=float(timeout) + 10) as client:
                resp = await client.post(
                    f"{agent_url}/ai/run",
                    headers={"Authorization": f"Bearer {agent_token}"},
                    json=agent_payload,
                )
            if resp.status_code == 200:
                result = resp.json()
            else:
                result = {"ok": False, "error": f"Agent HTTP {resp.status_code}: {resp.text[:500]}"}
        except httpx.TimeoutException:
            result = {"ok": False, "error": "Agent AI request timed out"}
        except httpx.ConnectError:
            result = {"ok": False, "error": f"Cannot connect to agent at {agent_url}"}
        except Exception as e:
            result = {"ok": False, "error": str(e)}
    else:
        # ── DIRECT CALL (fallback when no instance) ──
        payload = build_baseten_payload(input_data, system_prompt, input_schema, memory=memory)
        result = await call_baseten_model(
            api_url=app.get("baseten_api_url", ""),
            api_key=app.get("baseten_api_key", ""),
            model_id=app.get("baseten_model_id", ""),
            payload=payload,
            timeout=float(timeout),
        )

    # Update run record
    finished_at = datetime.now(timezone.utc).isoformat()
    latency_ms = result.get("latency_ms", 0)
    stored_files = result.get("stored_files") or result.get("files")

    if result.get("ok"):
        output_data = result.get("result", {})

        # If direct call, store outputs to R2 as fallback
        if not resolved_instance_id and isinstance(output_data, dict):
            r2_files = await store_output_to_r2(
                project_id, slug, run_id, output_data, output_folder,
            )
            if r2_files:
                stored_files = r2_files

        await db.update("ai_app_runs", run_id, {
            "output": output_data,
            "status": "success",
            "latency_ms": latency_ms,
            "credits_charged": app.get("credits_per_run", 0),
            "finished_at": finished_at,
        })
        # Increment total runs
        d = await db.get_db()
        await d.execute("UPDATE ai_apps SET total_runs = total_runs + 1 WHERE id = ?", [app["id"]])
        await d.commit()
    else:
        await db.update("ai_app_runs", run_id, {
            "status": "error",
            "error": result.get("error", "Unknown error"),
            "latency_ms": latency_ms,
            "finished_at": finished_at,
        })

    response = {
        "ok": result.get("ok", False),
        "run_id": run_id,
        "app": slug,
        "result": result.get("result") if result.get("ok") else None,
        "error": result.get("error") if not result.get("ok") else None,
        "latency_ms": latency_ms,
        "executed_on": "agent" if resolved_instance_id else "central",
    }

    if stored_files:
        response["files"] = stored_files

    return response


@project_router.get("/{slug}/runs")
async def list_project_runs(
    slug: str,
    limit: int = Query(50, ge=1, le=200),
    project_id: str = Depends(require_project),
):
    """List this project's execution history for an AI app."""
    app = await db.fetch_one("ai_apps", slug=slug)
    if not app:
        raise HTTPException(404, f"AI app '{slug}' not found")

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT id, status, latency_ms, credits_charged, error, created_at, finished_at "
        "FROM ai_app_runs WHERE app_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?",
        [app["id"], project_id, limit],
    )
    runs = [dict(r) for r in await cursor.fetchall()]
    return {"runs": runs, "count": len(runs)}


@project_router.get("/{slug}/runs/{run_id}")
async def get_run_detail(slug: str, run_id: str, project_id: str = Depends(require_project)):
    """Get full details of a specific run (including input/output)."""
    run = await db.fetch_one("ai_app_runs", id=run_id, project_id=project_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {"run": run}


@project_router.get("/{slug}/memory")
async def get_app_memory(slug: str, project_id: str = Depends(require_project)):
    """Get this project's memory/preferences for an AI app."""
    app = await db.fetch_one("ai_apps", slug=slug)
    if not app:
        raise HTTPException(404, f"AI app '{slug}' not found")

    memory = await gather_memory(project_id, app["id"], db)
    return {"memory": memory}


@project_router.put("/{slug}/memory")
async def update_app_memory(slug: str, request: Request, project_id: str = Depends(require_project)):
    """Update this project's preferences for an AI app.

    Example: {"output_folder": "images", "default_style": "minimal"}
    These preferences are injected as context into every run.
    """
    app = await db.fetch_one("ai_apps", slug=slug)
    if not app:
        raise HTTPException(404, f"AI app '{slug}' not found")

    try:
        prefs = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    if not isinstance(prefs, dict):
        raise HTTPException(400, "Body must be a JSON object")

    await save_memory(project_id, app["id"], prefs, db)
    return {"ok": True, "preferences": prefs}
