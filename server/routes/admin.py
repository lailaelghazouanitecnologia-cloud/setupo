"""
Admin API routes — user management, analytics, blockchain, fraud detection.
All admin actions are audit-logged with the admin's identity.
"""
import re
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from server.deps import require_admin, AuthContext
from server.core import analytics, blockchain
from server.core.errors import NsoError

logger = logging.getLogger("nso.admin")
router = APIRouter()

_USER_ID_RE = re.compile(r"^user_[a-f0-9]{24}$")


def _check_user_id(user_id: str):
    if not _USER_ID_RE.match(user_id):
        raise HTTPException(400, "Invalid user ID format")


def _admin_id(auth: AuthContext) -> str:
    """Extract admin identity for audit trail."""
    return auth.user_id or "admin_token"


# ── Request models ──

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


class UpdateUserRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    email: str | None = Field(None, min_length=3, max_length=254)
    role: Literal["user", "admin", "disabled"] | None = None
    verified: bool | None = None


# ── Dashboard overview ──

@router.get("/overview")
async def dashboard_overview(auth: AuthContext = Depends(require_admin)):
    """Quick admin dashboard overview."""
    return await analytics.get_dashboard_overview()


# ── User management ──

@router.get("/users")
async def list_users(
    search: str = "",
    role: str = "",
    sort: str = "created_at",
    order: str = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_admin),
):
    """List all users with search and pagination."""
    try:
        return await analytics.admin_list_users(
            search=search, role=role, sort=sort, order=order,
            limit=limit, offset=offset,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.get("/users/{user_id}")
async def get_user(user_id: str, auth: AuthContext = Depends(require_admin)):
    """Get full user details (no password)."""
    _check_user_id(user_id)
    try:
        return {"user": await analytics.admin_get_user(user_id)}
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, req: UpdateUserRequest,
    auth: AuthContext = Depends(require_admin),
):
    """Update user fields (admin only)."""
    _check_user_id(user_id)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        user = await analytics.admin_update_user(
            user_id, updates, admin_id=_admin_id(auth),
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "user": user}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str, req: ResetPasswordRequest,
    auth: AuthContext = Depends(require_admin),
):
    """Reset a user's password."""
    _check_user_id(user_id)
    try:
        await analytics.admin_reset_password(
            user_id, req.new_password, admin_id=_admin_id(auth),
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.post("/users/{user_id}/disable")
async def disable_user(user_id: str, auth: AuthContext = Depends(require_admin)):
    """Disable a user account."""
    _check_user_id(user_id)
    try:
        await analytics.admin_disable_user(
            user_id, admin_id=_admin_id(auth),
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.get("/users/{user_id}/activity")
async def user_activity(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_admin),
):
    """Get activity log for a specific user."""
    _check_user_id(user_id)
    activity = await analytics.get_user_activity(user_id, limit=limit, offset=offset)
    return {"activity": activity, "count": len(activity)}


# ── Analytics ──

@router.get("/analytics/revenue")
async def revenue_analytics(
    days: int = Query(30, ge=1, le=365),
    auth: AuthContext = Depends(require_admin),
):
    """Revenue analytics summary."""
    return await analytics.revenue_summary(days=days)


@router.get("/analytics/growth")
async def growth_analytics(
    days: int = Query(30, ge=1, le=365),
    auth: AuthContext = Depends(require_admin),
):
    """User growth analytics."""
    return await analytics.growth_summary(days=days)


@router.get("/analytics/activity")
async def recent_activity(
    limit: int = Query(100, ge=1, le=500),
    action: str = "",
    auth: AuthContext = Depends(require_admin),
):
    """Platform-wide recent activity."""
    activity = await analytics.get_recent_activity(limit=limit, action=action)
    return {"activity": activity, "count": len(activity)}


@router.get("/analytics/cashflow")
async def cashflow(
    granularity: str = Query("month", regex="^(day|week|month|year)$"),
    periods: int = Query(12, ge=1, le=365),
    auth: AuthContext = Depends(require_admin),
):
    """Cashflow analysis: inflow vs outflow by day/week/month/year."""
    try:
        return await analytics.cashflow_analysis(
            granularity=granularity, periods=periods,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/analytics/snapshot")
async def create_snapshot(auth: AuthContext = Depends(require_admin)):
    """Generate a full analytics snapshot now."""
    snapshot = await analytics.generate_snapshot()
    return {"ok": True, "snapshot": snapshot}


@router.get("/analytics/snapshots")
async def list_snapshots(
    limit: int = Query(24, ge=1, le=100),
    auth: AuthContext = Depends(require_admin),
):
    """Get recent analytics snapshots."""
    snapshots = await analytics.get_snapshots(limit=limit)
    return {"snapshots": snapshots, "count": len(snapshots)}


# ── Fraud detection ──

@router.post("/fraud/scan")
async def fraud_scan(auth: AuthContext = Depends(require_admin)):
    """Run comprehensive fraud detection scan."""
    results = await analytics.run_fraud_scan(admin_id=_admin_id(auth))
    return results


# ── Blockchain ledger ──

@router.get("/ledger/stats")
async def ledger_stats(auth: AuthContext = Depends(require_admin)):
    """Get global ledger statistics."""
    return await blockchain.get_global_stats()


@router.get("/ledger/users/{user_id}")
async def user_ledger(
    user_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_admin),
):
    """Get a user's blockchain ledger."""
    _check_user_id(user_id)
    try:
        chain = await blockchain.get_chain(user_id, limit=limit, offset=offset)
        length = await blockchain.get_chain_length(user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"blocks": chain, "total": length}


@router.post("/ledger/users/{user_id}/verify")
async def verify_user_chain(user_id: str, auth: AuthContext = Depends(require_admin)):
    """Verify integrity of a user's ledger chain."""
    _check_user_id(user_id)
    try:
        result = await blockchain.verify_chain(user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/ledger/verify-all")
async def verify_all_chains(auth: AuthContext = Depends(require_admin)):
    """Verify all user chains (can be slow for many users)."""
    result = await blockchain.verify_all_chains()
    return result


@router.get("/ledger/users/{user_id}/balance-proof")
async def balance_proof(user_id: str, auth: AuthContext = Depends(require_admin)):
    """Get cryptographic balance proof for a user."""
    _check_user_id(user_id)
    try:
        proof = await blockchain.get_balance_proof(user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return proof


@router.get("/ledger/discrepancies")
async def find_discrepancies(auth: AuthContext = Depends(require_admin)):
    """Find all balance discrepancies across all users."""
    discrepancies = await blockchain.find_discrepancies()
    return {"discrepancies": discrepancies, "count": len(discrepancies)}


# ── Projects & Workspaces (admin view) ──

@router.get("/projects")
async def admin_list_projects(
    search: str = "",
    sort: str = "created_at",
    order: str = "desc",
    limit: int = Query(50, le=200),
    offset: int = 0,
    auth: AuthContext = Depends(require_admin),
):
    """List all projects across all users with workspace count."""
    from server.core import db
    d = await db.get_db()

    direction = "DESC" if order == "desc" else "ASC"
    sort_col = sort if sort in ("created_at", "name") else "created_at"
    db._validate_identifier(sort_col, "column")

    if search:
        cursor = await d.execute(
            f"SELECT * FROM projects WHERE name LIKE ? OR id LIKE ? ORDER BY {sort_col} {direction} LIMIT ? OFFSET ?",
            (f"%{search}%", f"%{search}%", limit, offset),
        )
        count_cursor = await d.execute(
            "SELECT COUNT(*) FROM projects WHERE name LIKE ? OR id LIKE ?",
            (f"%{search}%", f"%{search}%"),
        )
    else:
        cursor = await d.execute(
            f"SELECT * FROM projects ORDER BY {sort_col} {direction} LIMIT ? OFFSET ?",
            (limit, offset),
        )
        count_cursor = await d.execute("SELECT COUNT(*) FROM projects")

    rows = await cursor.fetchall()
    total = (await count_cursor.fetchone())[0]

    projects = []
    for row in rows:
        p = db._row_to_dict(row)
        # Count workspaces
        ws_cursor = await d.execute(
            "SELECT COUNT(*) FROM workspaces WHERE project_id = ?", (p["id"],),
        )
        ws_count = (await ws_cursor.fetchone())[0]
        # Count instances
        inst_cursor = await d.execute(
            "SELECT COUNT(*) FROM instances WHERE project_id = ?", (p["id"],),
        )
        inst_count = (await inst_cursor.fetchone())[0]
        # Get owner info
        owner_email = ""
        if p.get("owner"):
            owner_row = await db.fetch_one("users", id=p["owner"])
            owner_email = owner_row.get("email", "") if owner_row else ""

        p["workspace_count"] = ws_count
        p["instance_count"] = inst_count
        p["owner_email"] = owner_email
        # Don't expose API key hash
        p.pop("api_key_hash", None)
        projects.append(p)

    return {"projects": projects, "total": total}


@router.get("/projects/{project_id}/workspaces")
async def admin_list_workspaces(
    project_id: str,
    auth: AuthContext = Depends(require_admin),
):
    """List all workspaces for a specific project."""
    from server.core import db
    d = await db.get_db()

    # Verify project exists
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    cursor = await d.execute(
        "SELECT * FROM workspaces WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    rows = await cursor.fetchall()
    workspaces = [db._row_to_dict(r) for r in rows]

    return {"workspaces": workspaces, "project": {
        "id": project["id"],
        "name": project["name"],
        "owner": project.get("owner", ""),
    }}


@router.get("/workspaces")
async def admin_list_all_workspaces(
    search: str = "",
    ws_type: str = "",
    limit: int = Query(100, le=500),
    offset: int = 0,
    auth: AuthContext = Depends(require_admin),
):
    """List all workspaces across all projects."""
    from server.core import db
    d = await db.get_db()

    conditions = []
    params: list = []

    if search:
        conditions.append("(w.name LIKE ? OR w.id LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if ws_type:
        conditions.append("w.ws_type = ?")
        params.append(ws_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor = await d.execute(
        f"""SELECT w.*, p.name as project_name, p.owner as owner_id
            FROM workspaces w
            LEFT JOIN projects p ON w.project_id = p.id
            {where}
            ORDER BY w.updated_at DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    rows = await cursor.fetchall()

    count_cursor = await d.execute(
        f"SELECT COUNT(*) FROM workspaces w {where}", params,
    )
    total = (await count_cursor.fetchone())[0]

    workspaces = []
    for row in rows:
        w = db._row_to_dict(row)
        # Get owner email
        owner_id = w.pop("owner_id", "")
        if owner_id:
            owner_row = await db.fetch_one("users", id=owner_id)
            w["owner_email"] = owner_row.get("email", "") if owner_row else ""
        else:
            w["owner_email"] = ""
        workspaces.append(w)

    return {"workspaces": workspaces, "total": total}


@router.get("/instances")
async def admin_list_all_instances(
    state: str = "",
    limit: int = Query(100, le=500),
    offset: int = 0,
    auth: AuthContext = Depends(require_admin),
):
    """List all instances across all projects."""
    from server.core import db
    d = await db.get_db()

    conditions = []
    params: list = []

    if state:
        conditions.append("i.state = ?")
        params.append(state)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor = await d.execute(
        f"""SELECT i.*, p.name as project_name
            FROM instances i
            LEFT JOIN projects p ON i.project_id = p.id
            {where}
            ORDER BY i.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    rows = await cursor.fetchall()

    count_cursor = await d.execute(
        f"SELECT COUNT(*) FROM instances i {where}", params,
    )
    total = (await count_cursor.fetchone())[0]

    instances = [db._row_to_dict(r) for r in rows]
    return {"instances": instances, "total": total}
