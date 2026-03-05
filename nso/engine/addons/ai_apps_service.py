"""NSO AI Apps — Baseten-powered AI service execution engine.

Admin publishes AI apps with a Baseten model endpoint + input schema.
Users call the apps via API from their deployed projects using their API key.
"""

import json
import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("nso.ai_apps")

_BASETEN_TIMEOUT = 120.0


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


def build_baseten_payload(input_data: dict, system_prompt: str = "", input_schema: dict | None = None) -> dict:
    """Build the payload to send to Baseten.

    Wraps user input into the standard Baseten predict format.
    If a system_prompt is set, it's included for chat/LLM models.
    """
    payload: dict = {}

    if system_prompt:
        payload["prompt"] = system_prompt
        payload["inputs"] = input_data
    else:
        payload.update(input_data)

    return payload
