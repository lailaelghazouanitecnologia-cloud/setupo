"""NSO Agent — AI App execution endpoint.

Receives AI app run requests from the central server and executes them
locally on the user's VPS. Handles Baseten model calls, output file storage,
and returns results back to the central server.

Same pattern as deploy.py and exec.py — authenticated via agent JWT.
"""

import base64
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("nso-agent.ai")
router = APIRouter(prefix="/ai", tags=["ai"])

ASSETS_DIR = Path("/opt/app/assets")
AI_TIMEOUT = 120.0


class AIRunRequest(BaseModel):
    """Request from central server to execute an AI app."""
    app_slug: str
    run_id: str
    api_url: str = ""
    api_key: str = ""
    model_id: str = ""
    payload: dict = Field(default_factory=dict)
    system_prompt: str = ""
    memory: dict = Field(default_factory=dict)
    timeout: float = 60.0
    output_folder: str = "assets"
    save_output: bool = True


class AIRunResponse(BaseModel):
    ok: bool
    run_id: str
    result: dict | None = None
    error: str = ""
    latency_ms: int = 0
    stored_files: dict = Field(default_factory=dict)


@router.post("/run", response_model=AIRunResponse)
async def run_ai_app(req: AIRunRequest, admin: AdminUser = Depends(require_admin)):
    """Execute an AI app on this agent.

    Central server proxies AI app requests here so they run
    on the user's VPS instance — same backend as deploy.
    """
    logger.info("AI run: app=%s run_id=%s", req.app_slug, req.run_id)

    # Build the model URL
    if req.api_url:
        url = req.api_url
    elif req.model_id:
        url = f"https://model-{req.model_id}.api.baseten.co/production/predict"
    else:
        return AIRunResponse(ok=False, run_id=req.run_id, error="No api_url or model_id provided")

    # Build request payload with memory context
    call_payload = _build_payload(req.payload, req.system_prompt, req.memory)

    # Call the AI model
    headers = {"Content-Type": "application/json"}
    if req.api_key:
        headers["Authorization"] = f"Api-Key {req.api_key}"

    start = time.monotonic()
    try:
        timeout = min(req.timeout, AI_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=call_payload)
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.warning("AI model call failed (%d): %s", resp.status_code, error_text)
            return AIRunResponse(
                ok=False, run_id=req.run_id,
                error=f"Model HTTP {resp.status_code}: {error_text}",
                latency_ms=latency_ms,
            )

        try:
            result = resp.json()
        except Exception:
            result = {"raw": resp.text[:5000]}

    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - start) * 1000)
        return AIRunResponse(ok=False, run_id=req.run_id, error="Model request timed out", latency_ms=latency_ms)
    except httpx.ConnectError as e:
        return AIRunResponse(ok=False, run_id=req.run_id, error=f"Cannot connect to model: {e}")
    except Exception as e:
        logger.exception("AI model call error")
        return AIRunResponse(ok=False, run_id=req.run_id, error=str(e))

    # Store output files locally in the app's assets folder
    stored_files = {}
    if req.save_output and isinstance(result, dict):
        stored_files = _store_output_files(req.app_slug, req.run_id, result, req.output_folder)

    logger.info("AI run complete: app=%s latency=%dms files=%d", req.app_slug, latency_ms, len(stored_files))

    return AIRunResponse(
        ok=True,
        run_id=req.run_id,
        result=result,
        latency_ms=latency_ms,
        stored_files=stored_files,
    )


@router.get("/assets")
async def list_assets(
    path: str = "",
    admin: AdminUser = Depends(require_admin),
):
    """List files in the AI assets directory."""
    target = ASSETS_DIR / path if path else ASSETS_DIR
    if not target.exists():
        return {"files": [], "path": str(target)}

    files = []
    for f in sorted(target.iterdir()):
        stat = f.stat()
        files.append({
            "name": f.name,
            "is_dir": f.is_dir(),
            "size": stat.st_size if f.is_file() else 0,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    return {"files": files, "path": str(target)}


def _build_payload(inputs: dict, system_prompt: str, memory: dict) -> dict:
    """Build the AI model payload with structured context injection.

    Memory is a rich dict with: project, workspaces, instances, domains,
    recent_runs, active_session, preferences. We format it into a readable
    context block for the model.
    """
    payload = {}

    if system_prompt:
        enriched = system_prompt
        if memory:
            context_block = _format_context(memory)
            if context_block:
                enriched = (
                    f"{system_prompt}\n\n"
                    f"--- Project Context ---\n"
                    f"{context_block}\n"
                    f"--- End Context ---"
                )
        payload["prompt"] = enriched
        payload["inputs"] = inputs
    else:
        payload.update(inputs)
        if memory:
            payload["_context"] = memory

    return payload


def _truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _format_context(memory: dict) -> str:
    """Format memory dict into a structured text block for prompt injection."""
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
            parts = [ws.get("name", "?")]
            if ws.get("stack"):
                parts.append(f"stack={ws['stack']}")
            if ws.get("type") and ws["type"] != "custom":
                parts.append(f"type={ws['type']}")
            if ws.get("git_url"):
                parts.append(f"git={ws['git_url']}")
            ws_lines.append("- " + " | ".join(parts))
        sections.append("## Workspaces\n" + "\n".join(ws_lines))

    # Instances
    instances = memory.get("instances", [])
    if instances:
        inst_lines = []
        for inst in instances:
            parts = [inst.get("label") or inst.get("id", "?")]
            if inst.get("state"):
                parts.append(f"state={inst['state']}")
            if inst.get("ip"):
                parts.append(f"ip={inst['ip']}")
            if inst.get("domain"):
                parts.append(f"domain={inst['domain']}")
            if inst.get("workspace"):
                parts.append(f"workspace={inst['workspace']}")
            inst_lines.append("- " + " | ".join(parts))
        sections.append("## Instances\n" + "\n".join(inst_lines))

    # Domains
    domains = memory.get("domains", [])
    if domains:
        dom_lines = [f"- {d.get('domain', '?')} ({d.get('type', 'A')})" for d in domains]
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
            f"- Collected: {_truncate(json.dumps(session.get('collected_data', {})))}\n"
            f"- Steps completed: {len(session.get('stage_history', []))}"
        )

    # Recent runs
    runs = memory.get("recent_runs", [])
    if runs:
        run_lines = []
        for run in runs[:5]:
            inp = _truncate(json.dumps(run.get("input", {})), 150)
            out = _truncate(json.dumps(run.get("output", {})), 150)
            status = run.get("status", "?")
            run_lines.append(f"- [{status}] {inp} → {out}")
        sections.append("## Recent Runs\n" + "\n".join(run_lines))

    # Backward compat: old flat memory format (project_name, preferences at top level)
    if not proj and memory.get("project_name"):
        sections.insert(0, f"## Project: {memory['project_name']}")
    if not prefs and memory.get("preferences") and isinstance(memory["preferences"], dict):
        pref_lines = [f"- {k}: {v}" for k, v in memory["preferences"].items()]
        if pref_lines:
            sections.append("## Preferences\n" + "\n".join(pref_lines))

    return "\n\n".join(sections)


def _store_output_files(app_slug: str, run_id: str, output: dict, folder: str) -> dict:
    """Detect and store file outputs (base64) to the local filesystem.

    Files saved to: /opt/app/{folder}/{app_slug}/{run_id}/{filename}
    """
    stored = {}
    base_dir = Path(f"/opt/app/{folder}/{app_slug}/{run_id}")

    for key, value in output.items():
        if not isinstance(value, str):
            continue

        file_data = None
        filename = key

        # data:image/png;base64,...
        if value.startswith("data:"):
            try:
                header, b64 = value.split(",", 1)
                content_type = header.split(":")[1].split(";")[0]
                file_data = base64.b64decode(b64)
                ext = content_type.split("/")[-1].split("+")[0]
                filename = f"{key}.{ext}"
            except Exception:
                continue

        # Raw base64 (long string, valid chars)
        elif len(value) > 1000:
            sample = value[:100]
            if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n" for c in sample):
                try:
                    file_data = base64.b64decode(value)
                    filename = f"{key}.bin"
                except Exception:
                    continue

        if file_data and len(file_data) > 0:
            try:
                base_dir.mkdir(parents=True, exist_ok=True)
                filepath = base_dir / filename
                filepath.write_bytes(file_data)
                stored[key] = {
                    "path": str(filepath),
                    "size": len(file_data),
                    "filename": filename,
                }
                logger.info("Stored AI output: %s → %s (%d bytes)", key, filepath, len(file_data))
            except Exception as e:
                logger.warning("Failed to store AI output %s: %s", key, e)

    return stored
