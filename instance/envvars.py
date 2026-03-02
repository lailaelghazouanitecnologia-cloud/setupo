import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("nso-agent.envvars")
router = APIRouter(prefix="/secrets", tags=["secrets"])

ENV_FILE = Path("/opt/nso/.env")
KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class SecretItem(BaseModel):
    key: str
    value: str
    bucket: str = "custom"


class SecretAddRequest(BaseModel):
    key: str
    value: str


class SecretUpdateRequest(BaseModel):
    value: str


BUCKETS = [
    {"name": "auth", "label": "Authentication", "prefixes": ["NSO_ADMIN", "AGENT_ADMIN", "JWT_", "SECRET_"]},
    {"name": "providers", "label": "Providers", "prefixes": ["VULTR_", "CF_"]},
    {"name": "storage", "label": "Storage (R2)", "prefixes": ["R2_"]},
    {"name": "system", "label": "System", "prefixes": ["HOST", "PORT", "DB_", "LOG_", "CORS_", "NSO_SERVE"]},
]


def _classify(key: str) -> str:
    for bucket in BUCKETS:
        if any(key.startswith(p) for p in bucket["prefixes"]):
            return bucket["name"]
    return "custom"

def _read_env() -> list[SecretItem]:
    if not ENV_FILE.exists():
        return []
    items = []
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        idx = line.index("=")
        key = line[:idx].strip()
        value = line[idx + 1:].strip()
        items.append(SecretItem(key=key, value=value, bucket=_classify(key)))
    return items


def _write_env(items: list[SecretItem]) -> None:
    lines: list[str] = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
    if lines and lines[-1] != "":
        lines.append("")
    for item in items:
        lines.append(f"{item.key}={item.value}")
    lines.append("")
    ENV_FILE.write_text("\n".join(lines))

@router.get("")
async def list_secrets(admin: AdminUser = Depends(require_admin)):
    items = _read_env()
    grouped: dict[str, list[dict]] = {}
    for item in items:
        bucket = item.bucket
        if bucket not in grouped:
            grouped[bucket] = []
        grouped[bucket].append({"key": item.key, "value": item.value})
    return {
        "secrets": [{"key": i.key, "value": i.value, "bucket": i.bucket} for i in items],
        "buckets": grouped,
        "count": len(items),
    }


@router.post("")
async def add_secret(req: SecretAddRequest, admin: AdminUser = Depends(require_admin)):
    key = req.key.strip().upper().replace(" ", "_")
    value = req.value.strip()

    if not key or not value:
        raise HTTPException(400, "Key and value are required")
    if not KEY_PATTERN.match(key):
        raise HTTPException(400, f"Invalid key format: must be uppercase letters, digits, underscores. Got: {key}")

    items = _read_env()
    for item in items:
        if item.key == key:
            raise HTTPException(409, f"Secret '{key}' already exists. Use PUT to update.")

    items.append(SecretItem(key=key, value=value, bucket=_classify(key)))
    _write_env(items)

    logger.info("Added secret: %s", key)
    return {"ok": True, "key": key, "bucket": _classify(key)}


@router.put("/{key}")
async def update_secret(key: str, req: SecretUpdateRequest, admin: AdminUser = Depends(require_admin)):
    key = key.upper()
    items = _read_env()
    found = False
    for item in items:
        if item.key == key:
            item.value = req.value.strip()
            found = True
            break
    if not found:
        raise HTTPException(404, f"Secret '{key}' not found")

    _write_env(items)
    logger.info("Updated secret: %s", key)
    return {"ok": True, "key": key}


@router.delete("/{key}")
async def delete_secret(key: str, admin: AdminUser = Depends(require_admin)):
    key = key.upper()
    items = _read_env()
    new_items = [i for i in items if i.key != key]
    if len(new_items) == len(items):
        raise HTTPException(404, f"Secret '{key}' not found")

    _write_env(new_items)
    logger.info("Deleted secret: %s", key)
    return {"ok": True, "key": key}


@router.get("/buckets")
async def list_buckets(admin: AdminUser = Depends(require_admin)):
    return {"buckets": BUCKETS + [{"name": "custom", "label": "Custom", "prefixes": []}]}
