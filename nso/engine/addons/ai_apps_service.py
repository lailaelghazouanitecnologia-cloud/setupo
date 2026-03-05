"""NSO AI Apps — Baseten-powered AI service execution engine.

Admin publishes AI apps with a Baseten model endpoint + input schema.
Users call the apps via API from their deployed projects using their API key.

Memory system: Each run injects context (project info, recent runs, preferences)
into the model payload so the AI agent has awareness of the user's history.
"""

import json
import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("nso.ai_apps")

_BASETEN_TIMEOUT = 120.0
_MEMORY_MAX_RUNS = 10  # max recent runs to include in context


async def gather_memory(project_id: str, app_id: str, db_module) -> dict:
    """Gather context/memory to inject into the AI agent.

    Collects:
    - Project info (name, workspaces)
    - Recent runs for this app+project (input/output history)
    - User preferences (output_folder, saved settings)

    This context is injected into the model so it has awareness
    of the user's history and can make smart decisions.
    """
    memory = {
        "project_id": project_id,
        "recent_runs": [],
        "preferences": {},
    }

    # Get project info
    project = await db_module.fetch_one("projects", id=project_id)
    if project:
        memory["project_name"] = project.get("name", "")

    # Get recent runs for context (last N successful runs)
    d = await db_module.get_db()
    cursor = await d.execute(
        "SELECT input, output, status, created_at "
        "FROM ai_app_runs WHERE app_id = ? AND project_id = ? AND status = 'success' "
        "ORDER BY created_at DESC LIMIT ?",
        [app_id, project_id, _MEMORY_MAX_RUNS],
    )
    rows = [dict(r) for r in await cursor.fetchall()]

    for row in rows:
        run_entry = {"created_at": row.get("created_at", "")}
        # Parse JSON fields
        for field in ("input", "output"):
            val = row.get(field, "{}")
            if isinstance(val, str):
                try:
                    run_entry[field] = json.loads(val)
                except Exception:
                    run_entry[field] = val
            else:
                run_entry[field] = val
        memory["recent_runs"].append(run_entry)

    # Get user preferences (stored in a memory table or config)
    pref = await db_module.fetch_one("ai_app_memory", project_id=project_id, app_id=app_id)
    if pref:
        prefs_data = pref.get("preferences", "{}")
        if isinstance(prefs_data, str):
            try:
                memory["preferences"] = json.loads(prefs_data)
            except Exception:
                memory["preferences"] = {}
        else:
            memory["preferences"] = prefs_data

    return memory


async def save_memory(project_id: str, app_id: str, preferences: dict, db_module):
    """Save/update user preferences for an app."""
    existing = await db_module.fetch_one("ai_app_memory", project_id=project_id, app_id=app_id)
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        # Merge preferences
        current_prefs = existing.get("preferences", {})
        if isinstance(current_prefs, str):
            try:
                current_prefs = json.loads(current_prefs)
            except Exception:
                current_prefs = {}
        current_prefs.update(preferences)
        await db_module.update("ai_app_memory", existing["id"], {
            "preferences": current_prefs,
            "updated_at": now,
        })
    else:
        import secrets as token_gen
        await db_module.insert("ai_app_memory", {
            "id": f"mem_{token_gen.token_hex(8)}",
            "project_id": project_id,
            "app_id": app_id,
            "preferences": preferences,
            "created_at": now,
            "updated_at": now,
        })


async def call_baseten_model(
    api_url: str,
    api_key: str,
    model_id: str,
    payload: dict,
    timeout: float = _BASETEN_TIMEOUT,
) -> dict:
    """Call a Baseten model endpoint and return the result.

    Baseten API format:
        POST https://model-{model_id}.api.baseten.co/production/predict
        Authorization: Api-Key {api_key}
        Body: {"inputs": {...}}

    If api_url is set, it overrides the default Baseten URL (custom endpoint).
    """
    if api_url:
        url = api_url
    elif model_id:
        url = f"https://model-{model_id}.api.baseten.co/production/predict"
    else:
        raise ValueError("Either api_url or model_id must be provided")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.warning("Baseten call failed (%d): %s", resp.status_code, error_text)
            return {
                "ok": False,
                "error": f"Model returned HTTP {resp.status_code}: {error_text}",
                "latency_ms": latency_ms,
            }

        try:
            result = resp.json()
        except Exception:
            result = {"raw": resp.text[:5000]}

        return {"ok": True, "result": result, "latency_ms": latency_ms}

    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"ok": False, "error": "Model request timed out", "latency_ms": latency_ms}
    except httpx.ConnectError as e:
        return {"ok": False, "error": f"Cannot connect to model endpoint: {e}", "latency_ms": 0}
    except Exception as e:
        logger.exception("Unexpected error calling Baseten model")
        return {"ok": False, "error": str(e), "latency_ms": 0}


def validate_input(input_data: dict, input_schema: dict) -> list[str]:
    """Basic validation of input data against the app's input schema.

    input_schema format:
    {
        "field_name": {
            "type": "text" | "number" | "select" | "textarea" | "file_url",
            "label": "Display Label",
            "required": true/false,
            "default": ...,
            "placeholder": "...",
            "options": [...],  # for select type
            "min": ..., "max": ...,  # for number type
        }
    }
    """
    errors = []
    for field_name, field_def in input_schema.items():
        if not isinstance(field_def, dict):
            continue
        required = field_def.get("required", False)
        value = input_data.get(field_name)

        if required and (value is None or value == ""):
            errors.append(f"Field '{field_name}' is required")
            continue

        if value is None or value == "":
            continue

        field_type = field_def.get("type", "text")
        if field_type == "number":
            try:
                num = float(value)
                if "min" in field_def and num < field_def["min"]:
                    errors.append(f"Field '{field_name}' must be >= {field_def['min']}")
                if "max" in field_def and num > field_def["max"]:
                    errors.append(f"Field '{field_name}' must be <= {field_def['max']}")
            except (TypeError, ValueError):
                errors.append(f"Field '{field_name}' must be a number")

        elif field_type == "select":
            options = field_def.get("options", [])
            if options and value not in options:
                errors.append(f"Field '{field_name}' must be one of: {', '.join(str(o) for o in options)}")

    return errors


def build_baseten_payload(
    input_data: dict,
    system_prompt: str = "",
    input_schema: dict | None = None,
    memory: dict | None = None,
) -> dict:
    """Build the payload to send to Baseten.

    Wraps user input into the standard Baseten predict format.
    If a system_prompt is set, it's included for chat/LLM models.
    If memory is provided, it's injected as context for the AI agent.
    """
    payload: dict = {}

    if system_prompt:
        # Inject memory into the system prompt so the AI has full context
        enriched_prompt = system_prompt
        if memory:
            context_parts = []
            if memory.get("project_name"):
                context_parts.append(f"Project: {memory['project_name']}")
            if memory.get("preferences"):
                prefs = memory["preferences"]
                output_folder = prefs.get("output_folder", "assets")
                context_parts.append(f"Output folder: {output_folder}")
                for k, v in prefs.items():
                    if k != "output_folder":
                        context_parts.append(f"{k}: {v}")
            if memory.get("recent_runs"):
                runs_summary = []
                for run in memory["recent_runs"][:5]:
                    inp = run.get("input", {})
                    out = run.get("output", {})
                    runs_summary.append(f"  - Input: {json.dumps(inp)[:200]} → Output: {json.dumps(out)[:200]}")
                context_parts.append("Recent history:\n" + "\n".join(runs_summary))

            if context_parts:
                enriched_prompt = f"{system_prompt}\n\n--- Context ---\n" + "\n".join(context_parts)

        payload["prompt"] = enriched_prompt
        payload["inputs"] = input_data
    else:
        payload.update(input_data)
        if memory:
            payload["_context"] = memory

    return payload


async def store_output_to_r2(
    project_id: str,
    app_slug: str,
    run_id: str,
    output_data: dict,
    output_folder: str = "assets",
) -> dict | None:
    """Store AI app output files in R2 under the project's assets path.

    R2 key format: {project_id}/{output_folder}/{app_slug}/{run_id}/{filename}

    If the output contains file data (base64, URLs), it gets stored in R2.
    Returns dict of stored file URLs.
    """
    from nso.engine.storage.service import R2Client
    from nso.config import settings
    import base64

    stored_files = {}

    # Look for file-like outputs (base64 data, image data, etc.)
    for key, value in output_data.items():
        if not isinstance(value, str):
            continue

        file_data = None
        content_type = "application/octet-stream"
        filename = f"{key}"

        # Base64-encoded file data
        if value.startswith("data:"):
            # data:image/png;base64,iVBOR...
            try:
                header, b64_data = value.split(",", 1)
                content_type = header.split(":")[1].split(";")[0]
                file_data = base64.b64decode(b64_data)
                ext = content_type.split("/")[-1].split("+")[0]
                filename = f"{key}.{ext}"
            except Exception:
                continue
        elif len(value) > 1000 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n" for c in value[:100]):
            # Raw base64 without data: prefix
            try:
                file_data = base64.b64decode(value)
                filename = f"{key}.bin"
            except Exception:
                continue

        if file_data and len(file_data) > 0:
            r2_key = f"{project_id}/{output_folder}/{app_slug}/{run_id}/{filename}"
            try:
                r2_cfg = settings.r2_config()
                async with R2Client(r2_cfg) as r2:
                    ok = await r2.upload(r2_key, file_data, content_type)
                if ok:
                    public_url = f"{r2_cfg.public_url}/{r2_key}" if r2_cfg.public_url else r2_key
                    stored_files[key] = {
                        "r2_key": r2_key,
                        "url": public_url,
                        "size": len(file_data),
                        "content_type": content_type,
                    }
                    logger.info("Stored AI output %s → %s (%d bytes)", key, r2_key, len(file_data))
            except Exception as e:
                logger.warning("Failed to store AI output %s to R2: %s", key, e)

    return stored_files if stored_files else None
