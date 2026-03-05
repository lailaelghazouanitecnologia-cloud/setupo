import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import require_admin, AdminUser

logger = logging.getLogger("z86-agent.envvars")
router = APIRouter(prefix="/secrets", tags=["secrets"])

BASE_ENV_FILE = Path("/opt/nso/.env")
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


# z86-specific bucket classifications
BUCKETS = [
    {"name": "z86", "label": "Z86 Storage", "prefixes": ["Z86_"]},
    {"name": "auth", "label": "Authentication", "prefixes": ["NSO_ADMIN", "AGENT_ADMIN", "JWT_", "SECRET_", "NSO_JWT_", "Z86_AGENT_", "Z86_JWT_"]},
    {"name": "storage", "label": "Storage (R2)", "prefixes": ["R2_"]},
    {"name": "system", "label": "System", "prefixes": [
        "NSO_HOST", "NSO_PORT", "NSO_DATA_", "NSO_CONFIG_",
        "NSO_AGENT_", "HOST", "PORT", "DB_", "LOG_",
    ]},
]


def _classify(key: str) -> str:
    for bucket in BUCKETS:
        if any(key.startswith(p) for p in bucket["prefixes"]):
            return bucket["name"]
    return "custom"


def _read_env(env_file: Path) -> list[SecretItem]:
    if not env_file.exists():
        return []
    items = []
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        idx = line.index("=")
        key = line[:idx].strip()
        value = line[idx + 1:].strip()
        items.append(SecretItem(key=key, value=value, bucket=_classify(key)))
    return items


def _write_env(items: list[SecretItem], env_file: Path) -> None:
    lines: list[str] = []
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
    if lines and lines[-1] != "":
        lines.append("")
    for item in items:
        lines.append(f"{item.key}={item.value}")
    lines.append("")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines))


@router.get("")
async def list_secrets(admin: AdminUser = Depends(require_admin)):
    items = _read_env(BASE_ENV_FILE)
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
async def add_secret(
    req: SecretAddRequest,
    admin: AdminUser = Depends(require_admin),
):
    key = req.key.strip().upper().replace(" ", "_")
    value = req.value.strip()

    if not key or not value:
        raise HTTPException(400, "Key and value are required")
    if not KEY_PATTERN.match(key):
        raise HTTPException(400, f"Invalid key format: must be uppercase letters, digits, underscores. Got: {key}")

    items = _read_env(BASE_ENV_FILE)
    for item in items:
        if item.key == key:
            raise HTTPException(409, f"Secret '{key}' already exists. Use PUT to update.")

    items.append(SecretItem(key=key, value=value, bucket=_classify(key)))
    _write_env(items, BASE_ENV_FILE)

    logger.info("Added secret: %s", key)
    return {"ok": True, "key": key, "bucket": _classify(key)}


@router.put("/{key}")
async def update_secret(
    key: str,
    req: SecretUpdateRequest,
    admin: AdminUser = Depends(require_admin),
):
    key = key.upper()
    items = _read_env(BASE_ENV_FILE)
    found = False
    for item in items:
        if item.key == key:
            item.value = req.value.strip()
            found = True
            break
    if not found:
        raise HTTPException(404, f"Secret '{key}' not found")

    _write_env(items, BASE_ENV_FILE)
    logger.info("Updated secret: %s", key)
    return {"ok": True, "key": key}


@router.delete("/{key}")
async def delete_secret(
    key: str,
    admin: AdminUser = Depends(require_admin),
):
    key = key.upper()
    items = _read_env(BASE_ENV_FILE)
    new_items = [i for i in items if i.key != key]
    if len(new_items) == len(items):
        raise HTTPException(404, f"Secret '{key}' not found")

    _write_env(new_items, BASE_ENV_FILE)
    logger.info("Deleted secret: %s", key)
    return {"ok": True, "key": key}


@router.get("/buckets")
async def list_buckets(admin: AdminUser = Depends(require_admin)):
    return {"buckets": BUCKETS + [{"name": "custom", "label": "Custom", "prefixes": []}]}
