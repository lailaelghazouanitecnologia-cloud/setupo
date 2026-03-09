import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project, require_project_owner
from nso.shared.secrets import BUCKETS, classify_secret

logger = logging.getLogger("nso.secrets")
router = APIRouter()

KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class SecretAddRequest(BaseModel):
    key: str
    value: str
    scope: str = "general"


class SecretUpdateRequest(BaseModel):
    value: str


class ScopeCreateRequest(BaseModel):
    name: str


# ── List secrets ──

@router.get("")
async def list_secrets(
    scope: str = Query("general"),
    project_id: str = Depends(require_project),
):
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM project_secrets WHERE project_id = ? AND scope = ? ORDER BY key ASC",
        (project_id, scope),
    )
    rows = await cursor.fetchall()
    secrets = [dict(r) for r in rows]

    grouped: dict[str, list[dict]] = {}
    for s in secrets:
        b = s.get("bucket", "custom")
        if b not in grouped:
            grouped[b] = []
        grouped[b].append({"key": s["key"], "value": s["value"]})

    return {
        "secrets": [{"key": s["key"], "value": s["value"], "bucket": s.get("bucket", "custom")} for s in secrets],
        "buckets": grouped,
        "count": len(secrets),
        "scope": scope,
    }


# ── Add secret ──

@router.post("")
async def add_secret(
    req: SecretAddRequest,
    project_id: str = Depends(require_project_owner),
):
    key = req.key.strip().upper().replace(" ", "_")
    value = req.value.strip()
    scope = req.scope.strip() or "general"

    if not key or not value:
        raise HTTPException(400, "Key and value are required")
    if not KEY_PATTERN.match(key):
        raise HTTPException(400, f"Invalid key format: must be uppercase letters, digits, underscores. Got: {key}")

    existing = await db.fetch_one("project_secrets", project_id=project_id, key=key, scope=scope)
    if existing:
        raise HTTPException(409, f"Secret '{key}' already exists in scope '{scope}'. Use PUT to update.")

    bucket = classify_secret(key)
    secret_id = f"sec_{uuid.uuid4().hex[:16]}"
    await db.insert("project_secrets", {
        "id": secret_id,
        "project_id": project_id,
        "key": key,
        "value": value,
        "bucket": bucket,
        "scope": scope,
    })

    logger.info("Added secret %s to project %s (scope=%s)", key, project_id, scope)
    return {"ok": True, "key": key, "bucket": bucket, "scope": scope}


# ── Update secret ──

@router.put("/{key}")
async def update_secret(
    key: str,
    req: SecretUpdateRequest,
    scope: str = Query("general"),
    project_id: str = Depends(require_project_owner),
):
    key = key.upper()
    existing = await db.fetch_one("project_secrets", project_id=project_id, key=key, scope=scope)
    if not existing:
        raise HTTPException(404, f"Secret '{key}' not found")

    conn = await db.get_db()
    await conn.execute(
        "UPDATE project_secrets SET value = ?, updated_at = ? WHERE id = ?",
        (req.value.strip(), datetime.utcnow().isoformat(), existing["id"]),
    )
    await conn.commit()

    logger.info("Updated secret %s in project %s (scope=%s)", key, project_id, scope)
    return {"ok": True, "key": key, "scope": scope}


# ── Delete secret ──

@router.delete("/{key}")
async def delete_secret(
    key: str,
    scope: str = Query("general"),
    project_id: str = Depends(require_project_owner),
):
    key = key.upper()
    existing = await db.fetch_one("project_secrets", project_id=project_id, key=key, scope=scope)
    if not existing:
        raise HTTPException(404, f"Secret '{key}' not found")

    await db.delete("project_secrets", existing["id"])
    logger.info("Deleted secret %s from project %s (scope=%s)", key, project_id, scope)
    return {"ok": True, "key": key, "scope": scope}


# ── Scopes ──

@router.get("/scopes")
async def list_scopes(
    project_id: str = Depends(require_project),
):
    conn = await db.get_db()

    # Always include "general"
    scopes = [{"id": "general", "label": "General", "type": "general", "domain": None}]

    # Count secrets per general scope
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM project_secrets WHERE project_id = ? AND scope = 'general'",
        (project_id,),
    )
    row = await cursor.fetchone()
    scopes[0]["count"] = dict(row)["cnt"] if row else 0

    # Get distinct domain scopes
    cursor = await conn.execute(
        "SELECT DISTINCT scope FROM project_secrets WHERE project_id = ? AND scope != 'general' ORDER BY scope",
        (project_id,),
    )
    rows = await cursor.fetchall()
    for r in rows:
        s = dict(r)["scope"]
        domain = s.replace("domain:", "") if s.startswith("domain:") else s
        # Count secrets in this scope
        c2 = await conn.execute(
            "SELECT COUNT(*) as cnt FROM project_secrets WHERE project_id = ? AND scope = ?",
            (project_id, s),
        )
        r2 = await c2.fetchone()
        count = dict(r2)["cnt"] if r2 else 0
        scopes.append({
            "id": s,
            "label": domain,
            "type": "domain",
            "domain": domain,
            "count": count,
        })

    return {"scopes": scopes, "count": len(scopes)}


@router.post("/scopes")
async def create_scope(
    req: ScopeCreateRequest,
    project_id: str = Depends(require_project_owner),
):
    name = req.name.strip().lower()
    if not name:
        raise HTTPException(400, "Scope name is required")
    scope_id = f"domain:{name}"

    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT COUNT(*) as cnt FROM project_secrets WHERE project_id = ? AND scope = ?",
        (project_id, scope_id),
    )
    row = await cursor.fetchone()
    # Scope is just a label — it exists if there are secrets or we create a placeholder
    # We don't need to block creation, just return ok

    logger.info("Created scope %s for project %s", scope_id, project_id)
    return {"ok": True, "scope": scope_id, "domain": name}


@router.delete("/scopes/{domain}")
async def delete_scope(
    domain: str,
    project_id: str = Depends(require_project_owner),
):
    if domain == "general":
        raise HTTPException(400, "Cannot delete the general scope")

    scope_id = f"domain:{domain}"
    conn = await db.get_db()
    await conn.execute(
        "DELETE FROM project_secrets WHERE project_id = ? AND scope = ?",
        (project_id, scope_id),
    )
    await conn.commit()

    logger.info("Deleted scope %s and its secrets from project %s", scope_id, project_id)
    return {"ok": True, "domain": domain}


# ── Buckets ──

@router.get("/buckets")
async def list_buckets(
    project_id: str = Depends(require_project),
):
    return {"buckets": BUCKETS + [{"name": "custom", "label": "Custom", "prefixes": []}]}
