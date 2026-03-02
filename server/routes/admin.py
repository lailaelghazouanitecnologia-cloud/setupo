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
