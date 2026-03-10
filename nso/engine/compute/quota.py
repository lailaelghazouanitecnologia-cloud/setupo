"""
Quota enforcement — standalone compute limits per project.

No billing dependency. Limits are stored in a simple `compute_quotas` table
with sensible defaults. Admins can override limits per project.

Usage:
    from nso.engine.compute.quota import check_quota, get_project_quota

    # Before allocating a VM:
    await check_quota(project_id, compute_plan_code)  # raises if over limit

    # Get quota info:
    quota = await get_project_quota(project_id)
"""

from __future__ import annotations

import logging

from nso.shared import db
from nso.shared.errors import ValidationError

logger = logging.getLogger("nso.compute.quota")


# ── Default limits (no custom quota set) ──
# Defaults match free tier: no managed instances allowed (BYOV only).

DEFAULT_MAX_VMS = 0
DEFAULT_MAX_VCPUS = 0
DEFAULT_MAX_RAM_MB = 0
DEFAULT_ALLOWED_PLANS: list[str] = []


# ── Migration ──

QUOTA_MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS compute_quotas (
        project_id TEXT PRIMARY KEY,
        max_vms INTEGER DEFAULT 0,
        max_vcpus INTEGER DEFAULT 0,
        max_ram_mb INTEGER DEFAULT 0,
        allowed_plans TEXT DEFAULT '[]',
        notes TEXT DEFAULT '',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    """,
]


# ── Quota lookup ──

async def get_project_quota(project_id: str) -> dict:
    """
    Get quota for a project. Returns custom quota if set, otherwise defaults.
    """
    row = await db.fetch_one("compute_quotas", project_id=project_id)
    if row:
        row = dict(row)
        allowed = row.get("allowed_plans", '["free","starter"]')
        if isinstance(allowed, str):
            import json
            try:
                allowed = json.loads(allowed)
            except Exception:
                allowed = DEFAULT_ALLOWED_PLANS
        return {
            "project_id": project_id,
            "max_vms": row.get("max_vms", DEFAULT_MAX_VMS),
            "max_vcpus": row.get("max_vcpus", DEFAULT_MAX_VCPUS),
            "max_ram_mb": row.get("max_ram_mb", DEFAULT_MAX_RAM_MB),
            "allowed_plans": allowed,
            "custom": True,
        }

    return {
        "project_id": project_id,
        "max_vms": DEFAULT_MAX_VMS,
        "max_vcpus": DEFAULT_MAX_VCPUS,
        "max_ram_mb": DEFAULT_MAX_RAM_MB,
        "allowed_plans": DEFAULT_ALLOWED_PLANS,
        "custom": False,
    }


async def set_project_quota(
    project_id: str,
    max_vms: int | None = None,
    max_vcpus: int | None = None,
    max_ram_mb: int | None = None,
    allowed_plans: list[str] | None = None,
    notes: str = "",
) -> dict:
    """Set or update custom quota for a project (admin only)."""
    import json
    from datetime import datetime, timezone

    existing = await db.fetch_one("compute_quotas", project_id=project_id)
    if existing:
        updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if max_vms is not None:
            updates["max_vms"] = max_vms
        if max_vcpus is not None:
            updates["max_vcpus"] = max_vcpus
        if max_ram_mb is not None:
            updates["max_ram_mb"] = max_ram_mb
        if allowed_plans is not None:
            updates["allowed_plans"] = json.dumps(allowed_plans)
        if notes:
            updates["notes"] = notes
        await db.update("compute_quotas", project_id, updates)
    else:
        await db.insert("compute_quotas", {
            "project_id": project_id,
            "max_vms": max_vms if max_vms is not None else DEFAULT_MAX_VMS,
            "max_vcpus": max_vcpus if max_vcpus is not None else DEFAULT_MAX_VCPUS,
            "max_ram_mb": max_ram_mb if max_ram_mb is not None else DEFAULT_MAX_RAM_MB,
            "allowed_plans": json.dumps(allowed_plans or DEFAULT_ALLOWED_PLANS),
            "notes": notes,
        })

    return await get_project_quota(project_id)


async def delete_project_quota(project_id: str) -> bool:
    """Remove custom quota, reverting to defaults."""
    try:
        conn = await db.get_db()
        await conn.execute("DELETE FROM compute_quotas WHERE project_id = ?", (project_id,))
        await conn.commit()
        return True
    except Exception:
        return False


# ── Counting ──

async def count_project_active_vms(project_id: str) -> int:
    """Count active VMs for a project."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT COUNT(*) as c FROM compute_vms "
        "WHERE project_id = ? AND status NOT IN ('destroyed', 'error')",
        (project_id,),
    )
    row = await cursor.fetchone()
    return row["c"] if row else 0


async def get_project_resource_usage(project_id: str) -> dict:
    """Get total vCPU and RAM used by a project's active VMs."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT COALESCE(SUM(vcpus), 0) as vcpus, COALESCE(SUM(ram_mb), 0) as ram "
        "FROM compute_vms WHERE project_id = ? "
        "AND status NOT IN ('destroyed', 'error')",
        (project_id,),
    )
    row = await cursor.fetchone()
    if row:
        return {"vcpus": row["vcpus"], "ram_mb": row["ram"]}
    return {"vcpus": 0, "ram_mb": 0}


# ── Enforcement ──

async def check_quota(project_id: str, compute_plan_code: str) -> dict:
    """
    Check if a project can allocate a new VM with the given compute plan.

    Raises ValidationError if quota exceeded or plan not allowed.
    Returns quota info dict on success.
    """
    quota = await get_project_quota(project_id)

    # 1. Check compute plan is allowed
    if compute_plan_code not in quota["allowed_plans"]:
        raise ValidationError(
            f"Compute plan '{compute_plan_code}' is not available for this project. "
            f"Allowed plans: {', '.join(quota['allowed_plans'])}"
        )

    # 2. Check VM count limit
    current_count = await count_project_active_vms(project_id)
    max_vms = quota["max_vms"]

    if max_vms != -1 and current_count >= max_vms:
        raise ValidationError(
            f"VM limit reached ({current_count}/{max_vms}). "
            f"Contact admin to increase your quota."
        )

    # 3. Check aggregate resource limits
    usage = await get_project_resource_usage(project_id)
    from nso.engine.compute import pool
    plan = await pool.get_plan(compute_plan_code)

    if plan:
        new_vcpus = usage["vcpus"] + plan["vcpus"]
        new_ram = usage["ram_mb"] + plan["ram_mb"]

        if quota["max_vcpus"] != -1 and new_vcpus > quota["max_vcpus"]:
            raise ValidationError(
                f"vCPU limit would be exceeded ({new_vcpus}/{quota['max_vcpus']}). "
                f"Contact admin to increase your quota."
            )

        if quota["max_ram_mb"] != -1 and new_ram > quota["max_ram_mb"]:
            raise ValidationError(
                f"RAM limit would be exceeded ({new_ram}MB/{quota['max_ram_mb']}MB). "
                f"Contact admin to increase your quota."
            )

    return {
        "project_id": project_id,
        "compute_plan": compute_plan_code,
        "current_vms": current_count,
        "max_vms": max_vms,
        "allowed": True,
    }


async def get_project_usage(project_id: str) -> dict:
    """Get a project's current resource usage vs. its quota limits."""
    quota = await get_project_quota(project_id)
    current_vms = await count_project_active_vms(project_id)
    usage = await get_project_resource_usage(project_id)

    return {
        "project_id": project_id,
        "quota": quota,
        "usage": {
            "vms": current_vms,
            "vcpus": usage["vcpus"],
            "ram_mb": usage["ram_mb"],
        },
        "remaining": {
            "vms": quota["max_vms"] - current_vms if quota["max_vms"] != -1 else -1,
            "vcpus": quota["max_vcpus"] - usage["vcpus"] if quota["max_vcpus"] != -1 else -1,
            "ram_mb": quota["max_ram_mb"] - usage["ram_mb"] if quota["max_ram_mb"] != -1 else -1,
        },
    }


async def get_owner_for_project(project_id: str) -> str | None:
    """Look up the owner (user_id) of a project."""
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        return None
    return project.get("owner")


# ── Plan-to-quota mapping ──

# These limits apply ONLY to managed instances (Vultr VPS created via NSO).
# BYOV (Bring Your Own VPS) servers are always unlimited — they don't cost us.
# max_vms = hard cap on managed instances for the billing tier.
# allowed_plans = which compute VM sizes (micro/small/medium/large) are available.
PLAN_QUOTA_MAP = {
    "free":  {"max_vms": 0,  "max_vcpus": 0,  "max_ram_mb": 0,     "allowed_plans": []},
    "hobby": {"max_vms": 1,  "max_vcpus": 1,  "max_ram_mb": 1024,  "allowed_plans": ["micro", "small"]},
    "pro":   {"max_vms": 3,  "max_vcpus": 8,  "max_ram_mb": 16384, "allowed_plans": ["micro", "small", "medium"]},
    "team":  {"max_vms": 10, "max_vcpus": 40, "max_ram_mb": 81920, "allowed_plans": ["micro", "small", "medium", "large"]},
}


async def sync_plan_to_quotas(user_id: str, plan_code: str) -> list[str]:
    """
    Sync billing plan to compute quotas for all projects owned by a user.

    Handles legacy plan codes (starter→hobby, scale→team) transparently.
    Called on subscription create, upgrade, downgrade, cancel, pause, resume.
    Returns list of project_ids that were updated.
    """
    # Resolve legacy plan codes
    from nso.engine.billing.service import LEGACY_PLAN_MAP
    resolved_code = LEGACY_PLAN_MAP.get(plan_code, plan_code)
    if resolved_code != plan_code:
        logger.info("Resolved legacy plan '%s' → '%s' for quota sync", plan_code, resolved_code)

    mapping = PLAN_QUOTA_MAP.get(resolved_code)
    if not mapping:
        logger.warning("No quota mapping for plan '%s' — skipping sync", resolved_code)
        return []

    # Find all projects owned by this user
    projects = await db.fetch_all("projects", owner=user_id)
    if not projects:
        logger.info("No projects for user %s — quota sync skipped", user_id)
        return []

    updated = []
    for project in projects:
        pid = project["id"]
        # Skip system project (admin infra)
        settings = project.get("settings")
        if isinstance(settings, str):
            import json as _json
            try:
                settings = _json.loads(settings)
            except Exception:
                settings = {}
        if isinstance(settings, dict) and settings.get("system"):
            continue

        await set_project_quota(
            project_id=pid,
            max_vms=mapping["max_vms"],
            max_vcpus=mapping["max_vcpus"],
            max_ram_mb=mapping["max_ram_mb"],
            allowed_plans=mapping["allowed_plans"],
            notes=f"Auto-synced from billing plan '{plan_code}'",
        )
        updated.append(pid)
        logger.info("Synced quota for project %s → plan '%s'", pid, plan_code)

    return updated
