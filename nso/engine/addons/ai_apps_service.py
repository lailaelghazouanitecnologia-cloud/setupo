"""NSO AI Apps — Baseten-powered AI service execution engine.

Admin publishes AI apps with a Baseten model endpoint + input schema.
Users call the apps via API from their deployed projects using their API key.

Memory system: Each run injects rich context (project, workspaces, instances,
domains, sessions, recent runs, preferences) into the model payload so the AI
agent has full awareness of the user's environment.
"""

import json
import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("nso.ai_apps")

_BASETEN_TIMEOUT = 120.0
_MEMORY_MAX_RUNS = 10
_MEMORY_MAX_SESSIONS = 5


# ─── Helpers ─────────────────────────────────────────────────────────

def _parse_json_field(value, fallback=None):
    """Safely parse a JSON string field from the DB."""
    if fallback is None:
        fallback = {}
    if isinstance(value, dict) or isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return fallback


def _truncate(text: str, max_len: int = 300) -> str:
    """Truncate text for context injection (avoid bloating the prompt)."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ─── Context Collectors ──────────────────────────────────────────────
# Each collector gathers one slice of context. They're composed in
# gather_memory() to build the full picture.

async def _collect_project(project_id: str, db_module) -> dict:
    """Project name + settings."""
    project = await db_module.fetch_one("projects", id=project_id)
    if not project:
        return {}
    return {
        "name": project.get("name", ""),
        "owner": project.get("owner", ""),
        "settings": _parse_json_field(project.get("settings", "{}")),
    }


async def _collect_workspaces(project_id: str, db_module) -> list[dict]:
    """All workspaces in the project (name, stack, git info)."""
    conn = await db_module.get_db()
    cursor = await conn.execute(
        "SELECT name, ws_type, stack, description, git_url, branch, instance_id "
        "FROM workspaces WHERE project_id = ? ORDER BY name",
        (project_id,),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return [
        {
            "name": r["name"],
            "type": r.get("ws_type", "custom"),
            "stack": r.get("stack", ""),
            "description": r.get("description", ""),
            "git_url": r.get("git_url", ""),
            "branch": r.get("branch", ""),
            "instance_id": r.get("instance_id", ""),
        }
        for r in rows
    ]


async def _collect_instances(project_id: str, db_module) -> list[dict]:
    """Active instances (ip, domain, state, workspace, plan)."""
    conn = await db_module.get_db()
    cursor = await conn.execute(
        "SELECT id, label, ip, domain, state, workspace, plan, region "
        "FROM instances WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return [
        {
            "id": r["id"],
            "label": r.get("label", ""),
            "ip": r.get("ip", ""),
            "domain": r.get("domain", ""),
            "state": r.get("state", ""),
            "workspace": r.get("workspace", ""),
            "plan": r.get("plan", ""),
            "region": r.get("region", ""),
        }
        for r in rows
    ]


async def _collect_domains(project_id: str, db_module) -> list[dict]:
    """Custom domains linked to the project."""
    conn = await db_module.get_db()
    cursor = await conn.execute(
        "SELECT domain, record_type, instance_id "
        "FROM domains WHERE project_id = ? ORDER BY domain",
        (project_id,),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return [
        {
            "domain": r["domain"],
            "type": r.get("record_type", "A"),
            "instance_id": r.get("instance_id", ""),
        }
        for r in rows
    ]


async def _collect_recent_runs(
    project_id: str, app_id: str, db_module, limit: int = _MEMORY_MAX_RUNS,
) -> list[dict]:
    """Recent app runs (input/output summaries)."""
    conn = await db_module.get_db()
    cursor = await conn.execute(
        "SELECT input, output, status, created_at "
        "FROM ai_app_runs WHERE app_id = ? AND project_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (app_id, project_id, limit),
    )
    runs = []
    for r in await cursor.fetchall():
        row = dict(r)
        runs.append({
            "input": _parse_json_field(row.get("input", "{}")),
            "output": _parse_json_field(row.get("output", "{}")),
            "status": row.get("status", ""),
            "created_at": row.get("created_at", ""),
        })
    return runs


async def _collect_active_session(
    project_id: str, app_id: str, db_module,
) -> dict | None:
    """Most recent active session for this app+project (if any)."""
    conn = await db_module.get_db()
    cursor = await conn.execute(
        "SELECT id, current_stage, current_stage_idx, collected_data, "
        "stage_outputs, stage_history, status, error "
        "FROM ai_app_sessions "
        "WHERE app_id = ? AND project_id = ? AND status = 'active' "
        "ORDER BY updated_at DESC LIMIT 1",
        (app_id, project_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    r = dict(row)
    return {
        "session_id": r["id"],
        "current_stage": r.get("current_stage", ""),
        "stage_index": r.get("current_stage_idx", 0),
        "collected_data": _parse_json_field(r.get("collected_data", "{}")),
        "stage_outputs": _parse_json_field(r.get("stage_outputs", "{}")),
        "stage_history": _parse_json_field(r.get("stage_history", "[]"), []),
        "status": r.get("status", "active"),
        "error": r.get("error", ""),
    }


async def _collect_preferences(
    project_id: str, app_id: str, db_module,
) -> dict:
    """User preferences for this app+project."""
    pref = await db_module.fetch_one(
        "ai_app_memory", project_id=project_id, app_id=app_id,
    )
    if not pref:
        return {}
    return _parse_json_field(pref.get("preferences", "{}"))


# ─── Main Memory API ─────────────────────────────────────────────────

async def gather_memory(project_id: str, app_id: str, db_module) -> dict:
    """Gather full project context + memory for AI agent injection.

    Returns a structured dict with:
    - project: name, owner, settings
    - workspaces: list of workspace summaries
    - instances: list of active instances
    - domains: custom domains
    - recent_runs: last N runs for this app
    - active_session: current in-progress session (if any)
    - preferences: user-saved preferences for this app
    """
    project = await _collect_project(project_id, db_module)
    workspaces = await _collect_workspaces(project_id, db_module)
    instances = await _collect_instances(project_id, db_module)
    domains = await _collect_domains(project_id, db_module)
    recent_runs = await _collect_recent_runs(project_id, app_id, db_module)
    active_session = await _collect_active_session(project_id, app_id, db_module)
    preferences = await _collect_preferences(project_id, app_id, db_module)

    return {
        "project": project,
        "workspaces": workspaces,
        "instances": instances,
        "domains": domains,
        "recent_runs": recent_runs,
        "active_session": active_session,
        "preferences": preferences,
    }


async def save_memory(project_id: str, app_id: str, preferences: dict, db_module):
    """Save/update user preferences for an app (merge into existing)."""
    existing = await db_module.fetch_one(
        "ai_app_memory", project_id=project_id, app_id=app_id,
    )
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        current_prefs = _parse_json_field(existing.get("preferences", "{}"))
        current_prefs.update(preferences)
        await db_module.update("ai_app_memory", existing["id"], {
            "preferences": json.dumps(current_prefs),
            "updated_at": now,
        })
    else:
        import secrets as token_gen
        await db_module.insert("ai_app_memory", {
            "id": f"mem_{token_gen.token_hex(8)}",
            "project_id": project_id,
            "app_id": app_id,
            "preferences": json.dumps(preferences),
            "created_at": now,
            "updated_at": now,
        })


# ─── Context → Prompt Formatting ─────────────────────────────────────

def format_context_block(memory: dict) -> str:
    """Format the gathered memory into a structured context block for prompt injection.

    Produces a clean, readable text block the AI model can reason about.
    """
    sections = []

    # Project
    proj = memory.get("project", {})
    if proj.get("name"):
        sections.append(f"## Project: {proj['name']}")
        if proj.get("owner"):
            sections.append(f"Owner: {proj['owner']}")

    # Workspaces
    workspaces = memory.get("workspaces", [])
    if workspaces:
        ws_lines = []
        for ws in workspaces:
            parts = [ws["name"]]
            if ws.get("stack"):
                parts.append(f"stack={ws['stack']}")
            if ws.get("type") and ws["type"] != "custom":
                parts.append(f"type={ws['type']}")
            if ws.get("git_url"):
                parts.append(f"git={ws['git_url']}")
                if ws.get("branch"):
                    parts.append(f"branch={ws['branch']}")
            ws_lines.append("- " + " | ".join(parts))
        sections.append("## Workspaces\n" + "\n".join(ws_lines))

    # Instances
    instances = memory.get("instances", [])
    if instances:
        inst_lines = []
        for inst in instances:
            parts = [inst.get("label") or inst["id"]]
            if inst.get("state"):
                parts.append(f"state={inst['state']}")
            if inst.get("ip"):
                parts.append(f"ip={inst['ip']}")
            if inst.get("domain"):
                parts.append(f"domain={inst['domain']}")
            if inst.get("workspace"):
                parts.append(f"workspace={inst['workspace']}")
            if inst.get("plan"):
                parts.append(f"plan={inst['plan']}")
            inst_lines.append("- " + " | ".join(parts))
        sections.append("## Instances\n" + "\n".join(inst_lines))

    # Domains
    domains = memory.get("domains", [])
    if domains:
        dom_lines = [f"- {d['domain']} ({d.get('type', 'A')})" for d in domains]
        sections.append("## Domains\n" + "\n".join(dom_lines))

    # Preferences
    prefs = memory.get("preferences", {})
    if prefs:
        pref_lines = [f"- {k}: {v}" for k, v in prefs.items()]
        sections.append("## User Preferences\n" + "\n".join(pref_lines))

    # Active session
    session = memory.get("active_session")
    if session:
        sections.append(
            f"## Active Session\n"
            f"- Stage: {session.get('current_stage', '?')} "
            f"(index {session.get('stage_index', 0)})\n"
            f"- Collected data: {_truncate(json.dumps(session.get('collected_data', {})))}\n"
            f"- History: {len(session.get('stage_history', []))} steps completed"
        )

    # Recent runs (compact)
    runs = memory.get("recent_runs", [])
    if runs:
        run_lines = []
        for run in runs[:5]:
            inp = _truncate(json.dumps(run.get("input", {})), 150)
            out = _truncate(json.dumps(run.get("output", {})), 150)
            status = run.get("status", "?")
            run_lines.append(f"- [{status}] {inp} → {out}")
        sections.append("## Recent Runs\n" + "\n".join(run_lines))

    return "\n\n".join(sections)


# ─── Baseten Integration ─────────────────────────────────────────────

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


# ─── Input Validation ─────────────────────────────────────────────────

def validate_input(input_data: dict, input_schema: dict) -> list[str]:
    """Validate input data against the app's input schema.

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


# ─── Payload Builder ──────────────────────────────────────────────────

def build_baseten_payload(
    input_data: dict,
    system_prompt: str = "",
    input_schema: dict | None = None,
    memory: dict | None = None,
) -> dict:
    """Build the payload to send to Baseten.

    Wraps user input into the standard Baseten predict format.
    If system_prompt is set, injects the formatted context block.
    If no system_prompt, attaches memory as _context for non-LLM models.
    """
    payload: dict = {}

    if system_prompt:
        enriched_prompt = system_prompt
        if memory:
            context_block = format_context_block(memory)
            if context_block:
                enriched_prompt = (
                    f"{system_prompt}\n\n"
                    f"--- Project Context ---\n"
                    f"{context_block}\n"
                    f"--- End Context ---"
                )
        payload["prompt"] = enriched_prompt
        payload["inputs"] = input_data
    else:
        payload.update(input_data)
        if memory:
            payload["_context"] = memory

    return payload


# ─── R2 Output Storage ────────────────────────────────────────────────

async def store_output_to_r2(
    project_id: str,
    app_slug: str,
    run_id: str,
    output_data: dict,
    output_folder: str = "assets",
) -> dict | None:
    """Store AI app output files in R2 under the project's assets path.

    R2 key format: {project_id}/{output_folder}/{app_slug}/{run_id}/{filename}

    Detects base64-encoded file data in output and uploads to R2.
    Returns dict of stored file metadata or None if nothing stored.
    """
    from nso.engine.storage.service import R2Client
    from nso.config import settings
    import base64

    stored_files = {}

    for key, value in output_data.items():
        if not isinstance(value, str):
            continue

        file_data = None
        content_type = "application/octet-stream"
        filename = key

        # data:image/png;base64,iVBOR...
        if value.startswith("data:"):
            try:
                header, b64_data = value.split(",", 1)
                content_type = header.split(":")[1].split(";")[0]
                file_data = base64.b64decode(b64_data)
                ext = content_type.split("/")[-1].split("+")[0]
                filename = f"{key}.{ext}"
            except Exception:
                continue
        elif len(value) > 1000 and all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n"
            for c in value[:100]
        ):
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
                    public_url = (
                        f"{r2_cfg.public_url}/{r2_key}" if r2_cfg.public_url else r2_key
                    )
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
