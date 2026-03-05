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
    """Build the AI model payload with context injection."""
    payload = {}

    if system_prompt:
        enriched = system_prompt
        if memory:
            context_parts = []
            if memory.get("project_name"):
                context_parts.append(f"Project: {memory['project_name']}")
            prefs = memory.get("preferences", {})
            if prefs:
                for k, v in prefs.items():
                    context_parts.append(f"{k}: {v}")
            runs = memory.get("recent_runs", [])
            if runs:
                summaries = []
                for r in runs[:5]:
                    inp = json.dumps(r.get("input", {}))[:200]
                    out = json.dumps(r.get("output", {}))[:200]
                    summaries.append(f"  - {inp} → {out}")
                context_parts.append("Recent history:\n" + "\n".join(summaries))

            if context_parts:
                enriched = f"{system_prompt}\n\n--- Context ---\n" + "\n".join(context_parts)

        payload["prompt"] = enriched
        payload["inputs"] = inputs
    else:
        payload.update(inputs)
        if memory:
            payload["_context"] = memory

    return payload


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
