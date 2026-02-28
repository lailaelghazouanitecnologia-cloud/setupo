"""
NSO Analytics — Platform-wide metrics, fraud detection, user behavior analysis.

Runs periodic analysis and produces snapshots stored in analytics_snapshots.
Tracks user activity via activity_log for last-seen, session analysis, and
behavioral anomaly detection. Admin actions are logged immutably in activity_log.
"""
import logging
import re
import secrets
from datetime import datetime, timezone, timedelta

from core import db
from core.errors import NotFoundError, ValidationError

logger = logging.getLogger("setupo.analytics")

_USER_ID_RE = re.compile(r"^user_[a-f0-9]{24}$")
_VALID_ROLES = frozenset({"user", "admin", "disabled"})
_MAX_SEARCH_LEN = 100
_ALLOWED_SORTS = {
    "created_at": "created_at",
    "email": "email",
    "name": "name",
    "balance": "balance",
    "last_active": "last_active",
}


def _validate_user_id(user_id: str):
    if not _USER_ID_RE.match(user_id):
        raise ValidationError("Invalid user_id format")


# ── Activity tracking ──

async def log_activity(
    user_id: str,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    ip: str = "",
    user_agent: str = "",
    metadata: dict | None = None,
):
    """Log a user activity event."""
    action = action[:64]
    resource_type = resource_type[:64]
    resource_id = resource_id[:128]
    ip = ip[:45]  # max IPv6 length
    user_agent = user_agent[:256]

    await db.insert("activity_log", {
        "id": f"act_{secrets.token_hex(12)}",
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "ip": ip,
        "user_agent": user_agent,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Update user last_active
    d = await db.get_db()
    await d.execute(
        "UPDATE users SET last_active = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    await d.commit()


async def _audit_admin_action(
    admin_id: str,
    action: str,
    target_user_id: str = "",
    details: dict | None = None,
):
    """Record an admin action in the audit trail (immutable in activity_log)."""
    await db.insert("activity_log", {
        "id": f"act_{secrets.token_hex(12)}",
        "user_id": admin_id or "admin_system",
        "action": f"admin.{action}",
        "resource_type": "user",
        "resource_id": target_user_id,
        "ip": "",
        "user_agent": "",
        "metadata": details or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def get_user_activity(
    user_id: str, limit: int = 50, offset: int = 0,
) -> list[dict]:
    """Get activity log for a specific user."""
    _validate_user_id(user_id)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM activity_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )
    return [db._row_to_dict(dict(r)) for r in await cursor.fetchall()]


async def get_recent_activity(limit: int = 100, action: str = "") -> list[dict]:
    """Get platform-wide recent activity."""
    limit = max(1, min(limit, 500))
    action = action[:64]

    d = await db.get_db()
    if action:
        cursor = await d.execute(
            "SELECT * FROM activity_log WHERE action = ? ORDER BY created_at DESC LIMIT ?",
            (action, limit),
        )
    else:
        cursor = await d.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    return [db._row_to_dict(dict(r)) for r in await cursor.fetchall()]


# ── Admin user management ──

async def admin_list_users(
    search: str = "",
    role: str = "",
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List users with search, filter, pagination for admin."""
    # Sanitize inputs
    search = search[:_MAX_SEARCH_LEN]
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    d = await db.get_db()
    conditions = []
    params: list = []

    if search:
        conditions.append("(email LIKE ? OR name LIKE ? OR id LIKE ?)")
        q = f"%{search}%"
        params.extend([q, q, q])
    if role:
        if role not in _VALID_ROLES:
            raise ValidationError(f"Invalid role filter: {role}")
        conditions.append("role = ?")
        params.append(role)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sort_col = _ALLOWED_SORTS.get(sort, "created_at")
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"

    cursor = await d.execute(
        f"SELECT COUNT(*) FROM users {where}", params,
    )
    total = (await cursor.fetchone())[0]

    cursor = await d.execute(
        f"SELECT id, email, name, role, balance, verified, subdomain, "
        f"last_active, created_at FROM users {where} "
        f"ORDER BY {sort_col} {sort_dir} LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    users = [db._row_to_dict(dict(r)) for r in await cursor.fetchall()]

    return {"users": users, "total": total, "limit": limit, "offset": offset}


async def admin_get_user(user_id: str) -> dict:
    """Get full user details for admin (no password)."""
    _validate_user_id(user_id)

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    safe = {k: v for k, v in user.items() if k != "password_hash"}

    # Enrich with billing data
    d = await db.get_db()

    cursor = await d.execute(
        "SELECT * FROM billing_subscriptions WHERE user_id = ? AND status IN ('active','trialing','paused') LIMIT 1",
        (user_id,),
    )
    sub_row = await cursor.fetchone()
    safe["subscription"] = db._row_to_dict(dict(sub_row)) if sub_row else None

    cursor = await d.execute(
        "SELECT COUNT(*) FROM billing_invoices WHERE user_id = ?", (user_id,),
    )
    safe["invoice_count"] = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT SUM(total_cents) FROM billing_invoices WHERE user_id = ? AND payment_status = 'succeeded'",
        (user_id,),
    )
    safe["total_paid_cents"] = (await cursor.fetchone())[0] or 0

    cursor = await d.execute(
        "SELECT SUM(balance_cents) FROM billing_wallets WHERE user_id = ? AND status = 'active'",
        (user_id,),
    )
    safe["wallet_balance_cents"] = (await cursor.fetchone())[0] or 0

    cursor = await d.execute(
        "SELECT COUNT(*) FROM activity_log WHERE user_id = ?", (user_id,),
    )
    safe["activity_count"] = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT COUNT(*) FROM projects WHERE owner = ?", (user_id,),
    )
    safe["project_count"] = (await cursor.fetchone())[0]

    return safe


async def admin_reset_password(user_id: str, new_password: str, admin_id: str = ""):
    """Admin resets a user's password (no current password needed)."""
    _validate_user_id(user_id)

    from server.auth.jwt import hash_password
    from core.users import _validate_password

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    _validate_password(new_password)

    pw_hash = hash_password(new_password)
    await db.update("users", user_id, {"password_hash": pw_hash})

    await _audit_admin_action(admin_id, "reset_password", user_id)
    logger.info("Admin %s reset password for user %s", admin_id, user_id)


async def admin_update_user(user_id: str, updates: dict, admin_id: str = "") -> dict:
    """Admin updates user fields (role, verified, name, email)."""
    _validate_user_id(user_id)

    allowed = {"role", "verified", "name", "email"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return await admin_get_user(user_id)

    # Validate individual fields
    if "role" in filtered:
        if filtered["role"] not in _VALID_ROLES:
            raise ValidationError(f"Invalid role: {filtered['role']}. Must be one of: {', '.join(_VALID_ROLES)}")

    if "name" in filtered:
        name = str(filtered["name"]).strip()
        if not name or len(name) > 64:
            raise ValidationError("Name must be 1-64 characters")
        filtered["name"] = name

    if "email" in filtered:
        from core.users import _validate_email
        filtered["email"] = _validate_email(filtered["email"])
        # Check uniqueness
        d = await db.get_db()
        cursor = await d.execute(
            "SELECT id FROM users WHERE email = ? AND id != ?",
            (filtered["email"], user_id),
        )
        if await cursor.fetchone():
            from core.errors import ConflictError
            raise ConflictError("Email already in use")

    if "verified" in filtered:
        filtered["verified"] = int(bool(filtered["verified"]))

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    await db.update("users", user_id, filtered)

    await _audit_admin_action(admin_id, "update_user", user_id, {
        "fields": list(filtered.keys()),
    })
    logger.info("Admin %s updated user %s: %s", admin_id, user_id, list(filtered.keys()))
    return await admin_get_user(user_id)


async def admin_disable_user(user_id: str, admin_id: str = ""):
    """Disable a user account. Admin cannot disable themselves."""
    _validate_user_id(user_id)

    if admin_id and user_id == admin_id:
        raise ValidationError("Cannot disable your own account")

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    if user.get("role") == "disabled":
        raise ValidationError("User is already disabled")

    await db.update("users", user_id, {"role": "disabled"})

    await _audit_admin_action(admin_id, "disable_user", user_id, {
        "previous_role": user.get("role"),
    })
    logger.info("Admin %s disabled user %s", admin_id, user_id)


# ── Revenue analytics ──

async def revenue_summary(days: int = 30) -> dict:
    """Revenue breakdown for the last N days."""
    days = max(1, min(days, 365))
    d = await db.get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Total revenue (paid invoices)
    cursor = await d.execute(
        "SELECT SUM(total_cents), COUNT(*) FROM billing_invoices "
        "WHERE payment_status = 'succeeded' AND created_at >= ?",
        (since,),
    )
    row = await cursor.fetchone()
    total_revenue_cents = row[0] or 0
    paid_invoices = row[1]

    # Revenue by plan
    cursor = await d.execute(
        "SELECT bs.plan_code, COUNT(*), SUM(bi.total_cents) "
        "FROM billing_invoices bi "
        "JOIN billing_subscriptions bs ON bi.subscription_id = bs.id "
        "WHERE bi.payment_status = 'succeeded' AND bi.created_at >= ? "
        "GROUP BY bs.plan_code",
        (since,),
    )
    by_plan = {}
    for row in await cursor.fetchall():
        by_plan[row[0]] = {"count": row[1], "revenue_cents": row[2] or 0}

    # Wallet top-ups (real money in)
    cursor = await d.execute(
        "SELECT SUM(amount) FROM billing_wallet_transactions "
        "WHERE transaction_type = 'inbound' AND source = 'topup' AND created_at >= ?",
        (since,),
    )
    wallet_topups = (await cursor.fetchone())[0] or 0

    # Refunds
    cursor = await d.execute(
        "SELECT SUM(total_cents), COUNT(*) FROM billing_credit_notes "
        "WHERE credit_type = 'refund' AND created_at >= ?",
        (since,),
    )
    row = await cursor.fetchone()
    refund_cents = row[0] or 0
    refund_count = row[1]

    # Daily revenue trend
    cursor = await d.execute(
        "SELECT DATE(created_at) as day, SUM(total_cents), COUNT(*) "
        "FROM billing_invoices "
        "WHERE payment_status = 'succeeded' AND created_at >= ? "
        "GROUP BY DATE(created_at) ORDER BY day",
        (since,),
    )
    daily_trend = [
        {"date": row[0], "revenue_cents": row[1] or 0, "count": row[2]}
        for row in await cursor.fetchall()
    ]

    return {
        "period_days": days,
        "total_revenue_cents": total_revenue_cents,
        "paid_invoices": paid_invoices,
        "wallet_topups_cents": int(wallet_topups * 100),
        "refund_cents": refund_cents,
        "refund_count": refund_count,
        "net_revenue_cents": total_revenue_cents - refund_cents,
        "by_plan": by_plan,
        "daily_trend": daily_trend,
    }


# ── User growth analytics ──

async def growth_summary(days: int = 30) -> dict:
    """User growth metrics."""
    days = max(1, min(days, 365))
    d = await db.get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    cursor = await d.execute("SELECT COUNT(*) FROM users")
    total_users = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT COUNT(*) FROM users WHERE created_at >= ?", (since,),
    )
    new_users = (await cursor.fetchone())[0]

    # Active users (had activity in period)
    cursor = await d.execute(
        "SELECT COUNT(DISTINCT user_id) FROM activity_log WHERE created_at >= ?",
        (since,),
    )
    active_users = (await cursor.fetchone())[0]

    # Daily signups
    cursor = await d.execute(
        "SELECT DATE(created_at) as day, COUNT(*) FROM users "
        "WHERE created_at >= ? GROUP BY DATE(created_at) ORDER BY day",
        (since,),
    )
    daily_signups = [
        {"date": row[0], "count": row[1]}
        for row in await cursor.fetchall()
    ]

    # Subscription distribution
    cursor = await d.execute(
        "SELECT plan_code, COUNT(*) FROM billing_subscriptions "
        "WHERE status IN ('active', 'trialing') GROUP BY plan_code",
    )
    plan_distribution = {row[0]: row[1] for row in await cursor.fetchall()}

    # Churn (cancelled in period)
    cursor = await d.execute(
        "SELECT COUNT(*) FROM billing_subscriptions "
        "WHERE status = 'cancelled' AND cancelled_at >= ?",
        (since,),
    )
    churned = (await cursor.fetchone())[0]

    return {
        "period_days": days,
        "total_users": total_users,
        "new_users": new_users,
        "active_users": active_users,
        "churned_users": churned,
        "churn_rate": round(churned / max(total_users, 1) * 100, 2),
        "daily_signups": daily_signups,
        "plan_distribution": plan_distribution,
    }


# ── Fraud detection ──

async def run_fraud_scan(admin_id: str = "") -> dict:
    """
    Run comprehensive fraud checks:
    1. Balance discrepancies (chain vs recorded)
    2. Suspicious patterns (large balances without matching payments)
    3. Chain integrity violations
    4. Unusual activity spikes
    """
    from core import blockchain

    results = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "triggered_by": admin_id or "system",
        "balance_discrepancies": [],
        "chain_violations": [],
        "suspicious_accounts": [],
        "anomalies": [],
    }

    # 1. Check blockchain integrity
    chain_result = await blockchain.verify_all_chains()
    if chain_result["invalid_count"] > 0:
        results["chain_violations"] = chain_result["corrupted_users"]

    # 2. Check balance discrepancies
    discrepancies = await blockchain.find_discrepancies()
    results["balance_discrepancies"] = discrepancies

    # 3. Suspicious accounts — high balance but no payment records
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT u.id, u.email, u.balance, u.created_at FROM users u "
        "WHERE u.balance > 100 AND u.id NOT IN ("
        "  SELECT DISTINCT user_id FROM billing_invoices WHERE payment_status = 'succeeded'"
        ") AND u.id NOT IN ("
        "  SELECT DISTINCT user_id FROM billing_wallets"
        ")"
    )
    for row in await cursor.fetchall():
        results["suspicious_accounts"].append({
            "user_id": row[0],
            "email": row[1],
            "balance": row[2],
            "created_at": row[3],
            "reason": "High balance with no payment history",
        })

    # 4. Anomalies — users with unusual activity volume (>100 actions in 1 hour)
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    cursor = await d.execute(
        "SELECT user_id, COUNT(*) as cnt FROM activity_log "
        "WHERE created_at >= ? GROUP BY user_id HAVING cnt > 100",
        (one_hour_ago,),
    )
    for row in await cursor.fetchall():
        results["anomalies"].append({
            "user_id": row[0],
            "action_count": row[1],
            "period": "1h",
            "reason": "Unusual activity spike",
        })

    # 5. Failed payments
    cursor = await d.execute(
        "SELECT user_id, COUNT(*) as cnt FROM billing_events "
        "WHERE event_type = 'payment.failed' AND created_at >= ? "
        "GROUP BY user_id HAVING cnt >= 3",
        ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),),
    )
    for row in await cursor.fetchall():
        results["anomalies"].append({
            "user_id": row[0],
            "failed_payments": row[1],
            "period": "7d",
            "reason": "Repeated payment failures",
        })

    total_issues = (
        len(results["balance_discrepancies"]) +
        len(results["chain_violations"]) +
        len(results["suspicious_accounts"]) +
        len(results["anomalies"])
    )
    results["total_issues"] = total_issues
    results["status"] = "clean" if total_issues == 0 else "issues_found"

    # Audit the scan itself
    if admin_id:
        await _audit_admin_action(admin_id, "fraud_scan", details={
            "total_issues": total_issues,
            "status": results["status"],
        })

    logger.info("Fraud scan complete: %d issues found (by %s)", total_issues, admin_id or "system")
    return results


# ── Snapshot generation ──

async def generate_snapshot() -> dict:
    """
    Generate a complete analytics snapshot. Run periodically (e.g. hourly).
    Stores in analytics_snapshots for historical trend analysis.
    """
    revenue = await revenue_summary(days=30)
    growth = await growth_summary(days=30)
    fraud = await run_fraud_scan()

    d = await db.get_db()

    # Infrastructure metrics
    cursor = await d.execute("SELECT COUNT(*) FROM instances WHERE state = 'active'")
    active_instances = (await cursor.fetchone())[0]

    cursor = await d.execute("SELECT COUNT(*) FROM projects")
    total_projects = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT COUNT(*) FROM billing_subscriptions WHERE status IN ('active','trialing')"
    )
    active_subs = (await cursor.fetchone())[0]

    snapshot = {
        "id": f"snap_{secrets.token_hex(12)}",
        "snapshot_type": "full",
        "revenue": revenue,
        "growth": growth,
        "fraud": {
            "status": fraud["status"],
            "total_issues": fraud["total_issues"],
            "balance_discrepancies": len(fraud["balance_discrepancies"]),
            "chain_violations": len(fraud["chain_violations"]),
        },
        "infrastructure": {
            "active_instances": active_instances,
            "total_projects": total_projects,
            "active_subscriptions": active_subs,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.insert("analytics_snapshots", {
        "id": snapshot["id"],
        "snapshot_type": "full",
        "data": snapshot,
        "created_at": snapshot["created_at"],
    })

    logger.info("Analytics snapshot created: %s", snapshot["id"])
    return snapshot


async def get_snapshots(limit: int = 24) -> list[dict]:
    """Get recent analytics snapshots."""
    limit = max(1, min(limit, 100))
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM analytics_snapshots ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return [db._row_to_dict(dict(r)) for r in await cursor.fetchall()]


async def get_dashboard_overview() -> dict:
    """
    Quick overview for the admin dashboard. Lightweight, no heavy scans.
    """
    d = await db.get_db()

    # Users
    cursor = await d.execute("SELECT COUNT(*) FROM users")
    total_users = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT COUNT(*) FROM users WHERE created_at >= ?",
        ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),),
    )
    new_users_7d = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT COUNT(DISTINCT user_id) FROM activity_log WHERE created_at >= ?",
        ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),),
    )
    dau = (await cursor.fetchone())[0]

    # Revenue
    cursor = await d.execute(
        "SELECT SUM(total_cents) FROM billing_invoices WHERE payment_status = 'succeeded'"
    )
    total_revenue_cents = (await cursor.fetchone())[0] or 0

    cursor = await d.execute(
        "SELECT SUM(total_cents) FROM billing_invoices "
        "WHERE payment_status = 'succeeded' AND created_at >= ?",
        ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),),
    )
    mrr_cents = (await cursor.fetchone())[0] or 0

    # Subscriptions
    cursor = await d.execute(
        "SELECT plan_code, COUNT(*) FROM billing_subscriptions "
        "WHERE status IN ('active', 'trialing') GROUP BY plan_code"
    )
    plan_dist = {row[0]: row[1] for row in await cursor.fetchall()}

    cursor = await d.execute(
        "SELECT COUNT(*) FROM billing_subscriptions WHERE status IN ('active', 'trialing')"
    )
    active_subs = (await cursor.fetchone())[0]

    # Infrastructure
    cursor = await d.execute("SELECT COUNT(*) FROM instances WHERE state = 'active'")
    active_instances = (await cursor.fetchone())[0]

    cursor = await d.execute("SELECT COUNT(*) FROM projects")
    total_projects = (await cursor.fetchone())[0]

    # Recent fraud status
    cursor = await d.execute(
        "SELECT data FROM analytics_snapshots WHERE snapshot_type = 'full' "
        "ORDER BY created_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    last_fraud_status = "unknown"
    if row:
        snap_data = db._row_to_dict(dict(row)).get("data", {})
        if isinstance(snap_data, dict):
            last_fraud_status = snap_data.get("fraud", {}).get("status", "unknown")

    return {
        "users": {
            "total": total_users,
            "new_7d": new_users_7d,
            "dau": dau,
        },
        "revenue": {
            "total_cents": total_revenue_cents,
            "mrr_cents": mrr_cents,
        },
        "subscriptions": {
            "active": active_subs,
            "plan_distribution": plan_dist,
        },
        "infrastructure": {
            "active_instances": active_instances,
            "total_projects": total_projects,
        },
        "fraud_status": last_fraud_status,
    }
