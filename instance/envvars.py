import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("nso-agent.envvars")
router = APIRouter(prefix="/secrets", tags=["secrets"])

BASE_ENV_FILE = Path("/opt/nso/.env")
DOMAINS_DIR = Path("/opt/nso/domains")
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


class CreateScopeRequest(BaseModel):
    domain: str


BUCKETS = [
    {"name": "auth", "label": "Authentication", "prefixes": ["NSO_ADMIN", "AGENT_ADMIN", "JWT_", "SECRET_", "NSO_JWT_"]},
    {"name": "providers", "label": "Providers", "prefixes": ["VULTR_", "CF_"]},
    {"name": "storage", "label": "Storage (R2)", "prefixes": ["R2_"]},
    {"name": "system", "label": "System", "prefixes": [
        "NSO_HOST", "NSO_PORT", "NSO_DATA_", "NSO_CONFIG_", "NSO_WORKSPACES_",
        "NSO_CORS_", "NSO_BASE_", "NSO_AGENT_", "NSO_SERVE",
        "HOST", "PORT", "DB_", "LOG_", "CORS_",
    ]},
]


def _classify(key: str) -> str:
    for bucket in BUCKETS:
        if any(key.startswith(p) for p in bucket["prefixes"]):
            return bucket["name"]
    return "custom"


def _env_file_for_scope(scope: str) -> Path:
    """Resolve the .env file path for a given scope."""
    if scope == "general":
        return BASE_ENV_FILE
    if scope.startswith("domain:"):
        domain = scope[7:]
        if not domain or "/" in domain or "\\" in domain or ".." in domain:
            raise HTTPException(400, f"Invalid domain in scope: {domain}")
        domain_dir = DOMAINS_DIR / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        return domain_dir / ".env"
    raise HTTPException(400, f"Invalid scope: {scope}. Use 'general' or 'domain:<name>'")


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


# ── Scopes ──

@router.get("/scopes")
async def list_scopes(admin: AdminUser = Depends(require_admin)):
    """List available secret scopes: general + domain scopes."""
    scopes = [{"id": "general", "label": "General", "type": "general", "domain": None}]

    if DOMAINS_DIR.exists():
        for domain_dir in sorted(DOMAINS_DIR.iterdir()):
            if domain_dir.is_dir() and not domain_dir.name.startswith("."):
                env_file = domain_dir / ".env"
                count = len(_read_env(env_file)) if env_file.exists() else 0
                scopes.append({
                    "id": f"domain:{domain_dir.name}",
                    "label": domain_dir.name,
                    "type": "domain",
                    "domain": domain_dir.name,
                    "count": count,
                })

    return {"scopes": scopes, "count": len(scopes)}


@router.post("/scopes")
async def create_scope(req: CreateScopeRequest, admin: AdminUser = Depends(require_admin)):
    """Create a new domain scope (creates the directory)."""
    domain = req.domain.strip().lower()
    if not domain:
        raise HTTPException(400, "Domain is required")
    if "/" in domain or "\\" in domain or ".." in domain:
        raise HTTPException(400, "Invalid domain name")

    domain_dir = DOMAINS_DIR / domain
    if domain_dir.exists():
        raise HTTPException(409, f"Scope for domain '{domain}' already exists")

    domain_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Created secret scope for domain: %s", domain)
    return {"ok": True, "scope": f"domain:{domain}", "domain": domain}


@router.delete("/scopes/{domain}")
async def delete_scope(domain: str, admin: AdminUser = Depends(require_admin)):
    """Delete a domain scope and all its secrets."""
    if domain == "general":
        raise HTTPException(400, "Cannot delete the general scope")

    domain_dir = DOMAINS_DIR / domain
    if not domain_dir.exists():
        raise HTTPException(404, f"Scope for domain '{domain}' not found")

    # Remove the .env file and directory
    env_file = domain_dir / ".env"
    if env_file.exists():
        env_file.unlink()
    try:
        domain_dir.rmdir()
    except OSError:
        # Directory not empty — remove remaining files
        import shutil
        shutil.rmtree(domain_dir)

    logger.info("Deleted secret scope for domain: %s", domain)
    return {"ok": True, "domain": domain}


# ── Secrets CRUD (with scope) ──

@router.get("")
async def list_secrets(
    scope: str = Query("general", description="Scope: 'general' or 'domain:<name>'"),
    admin: AdminUser = Depends(require_admin),
):
    env_file = _env_file_for_scope(scope)
    items = _read_env(env_file)
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
        "scope": scope,
    }


@router.post("")
async def add_secret(
    req: SecretAddRequest,
    scope: str = Query("general"),
    admin: AdminUser = Depends(require_admin),
):
    key = req.key.strip().upper().replace(" ", "_")
    value = req.value.strip()

    if not key or not value:
        raise HTTPException(400, "Key and value are required")
    if not KEY_PATTERN.match(key):
        raise HTTPException(400, f"Invalid key format: must be uppercase letters, digits, underscores. Got: {key}")

    env_file = _env_file_for_scope(scope)
    items = _read_env(env_file)
    for item in items:
        if item.key == key:
            raise HTTPException(409, f"Secret '{key}' already exists. Use PUT to update.")

    items.append(SecretItem(key=key, value=value, bucket=_classify(key)))
    _write_env(items, env_file)

    logger.info("Added secret: %s (scope=%s)", key, scope)
    return {"ok": True, "key": key, "bucket": _classify(key), "scope": scope}


@router.put("/{key}")
async def update_secret(
    key: str,
    req: SecretUpdateRequest,
    scope: str = Query("general"),
    admin: AdminUser = Depends(require_admin),
):
    key = key.upper()
    env_file = _env_file_for_scope(scope)
    items = _read_env(env_file)
    found = False
    for item in items:
        if item.key == key:
            item.value = req.value.strip()
            found = True
            break
    if not found:
        raise HTTPException(404, f"Secret '{key}' not found")

    _write_env(items, env_file)
    logger.info("Updated secret: %s (scope=%s)", key, scope)
    return {"ok": True, "key": key, "scope": scope}


@router.delete("/{key}")
async def delete_secret(
    key: str,
    scope: str = Query("general"),
    admin: AdminUser = Depends(require_admin),
):
    key = key.upper()
    env_file = _env_file_for_scope(scope)
    items = _read_env(env_file)
    new_items = [i for i in items if i.key != key]
    if len(new_items) == len(items):
        raise HTTPException(404, f"Secret '{key}' not found")

    _write_env(new_items, env_file)
    logger.info("Deleted secret: %s (scope=%s)", key, scope)
    return {"ok": True, "key": key, "scope": scope}


@router.get("/buckets")
async def list_buckets(admin: AdminUser = Depends(require_admin)):
    return {"buckets": BUCKETS + [{"name": "custom", "label": "Custom", "prefixes": []}]}
