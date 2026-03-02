"""
nso-billing — Core billing engine.

Inspired by Lago (event-based metering, billable metrics, credit notes, coupons)
and BoxBilling (hosting lifecycle, proration, tax).

Handles: plans, subscriptions, usage events, billable metrics, invoicing,
coupons/discounts, credit notes, wallets (prepaid), tax calculation,
payment method management, Stripe integration, and internal billing events.
"""
import logging
import secrets as token_gen
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

from server.core import db
from server.core.errors import NotFoundError, ConflictError, ValidationError

logger = logging.getLogger("nso.billing")


# ──────────────────────────────────────────────
#  Enums & Constants
# ──────────────────────────────────────────────

class PlanInterval(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    HOURLY = "hourly"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"
    VOID = "void"


class PaymentMethodType(str, Enum):
    CARD = "card"
    GOOGLE_PAY = "google_pay"
    APPLE_PAY = "apple_pay"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"


class CouponType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class CouponFrequency(str, Enum):
    ONCE = "once"
    RECURRING = "recurring"
    FOREVER = "forever"


class AggregationType(str, Enum):
    COUNT = "count"
    SUM = "sum"
    MAX = "max"
    LATEST = "latest"
    WEIGHTED_SUM = "weighted_sum"
    COUNT_DISTINCT = "count_distinct"


class CreditNoteType(str, Enum):
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    PRORATION = "proration"


class BillingEventType(str, Enum):
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_UPGRADED = "subscription.upgraded"
    SUBSCRIPTION_DOWNGRADED = "subscription.downgraded"
    INVOICE_GENERATED = "invoice.generated"
    INVOICE_FINALIZED = "invoice.finalized"
    INVOICE_PAID = "invoice.paid"
    INVOICE_VOIDED = "invoice.voided"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    COUPON_APPLIED = "coupon.applied"
    COUPON_REMOVED = "coupon.removed"
    CREDIT_NOTE_CREATED = "credit_note.created"
    USAGE_RECORDED = "usage.recorded"
    WALLET_CREDITED = "wallet.credited"
    WALLET_DEBITED = "wallet.debited"


CURRENCY = "USD"
GRACE_PERIOD_DAYS = 3


# ──────────────────────────────────────────────
#  Internal Billing Event Log
# ──────────────────────────────────────────────

async def _emit_event(
    event_type: str, resource_type: str = "", resource_id: str = "",
    user_id: str = "", data: dict | None = None,
):
    """Record an internal billing event for audit trail."""
    await db.insert("billing_events", {
        "id": f"be_{token_gen.token_hex(10)}",
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "user_id": user_id,
        "data": data or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def list_billing_events(
    user_id: str | None = None, event_type: str | None = None, limit: int = 50,
) -> list[dict]:
    """List billing events with optional filters."""
    d = await db.get_db()
    conditions = []
    params: list = []
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await d.execute(
        f"SELECT * FROM billing_events {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    )
    rows = await cursor.fetchall()
    return [db._row_to_dict(r) for r in rows]


# ──────────────────────────────────────────────
#  Default Plans (seeded on first access)
# ──────────────────────────────────────────────

DEFAULT_PLANS = [
    {
        "code": "free",
        "name": "Free",
        "description": "Get started — 1 instance, 1 GB storage, community support.",
        "interval": "monthly",
        "amount_cents": 0,
        "trial_days": 0,
        "features": {
            "instances": 1,
            "storage_gb": 1,
            "bandwidth_gb": 10,
            "workspaces": 2,
            "deploys_per_day": 5,
            "support": "community",
        },
    },
    {
        "code": "starter",
        "name": "Starter",
        "description": "For side projects — 3 instances, 10 GB storage, email support.",
        "interval": "monthly",
        "amount_cents": 900,
        "trial_days": 14,
        "features": {
            "instances": 3,
            "storage_gb": 10,
            "bandwidth_gb": 100,
            "workspaces": 10,
            "deploys_per_day": 50,
            "support": "email",
        },
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "For production — 10 instances, 50 GB storage, priority support.",
        "interval": "monthly",
        "amount_cents": 2900,
        "trial_days": 14,
        "features": {
            "instances": 10,
            "storage_gb": 50,
            "bandwidth_gb": 500,
            "workspaces": 50,
            "deploys_per_day": -1,
            "support": "priority",
        },
    },
    {
        "code": "scale",
        "name": "Scale",
        "description": "For teams — unlimited instances, 200 GB storage, dedicated support.",
        "interval": "monthly",
        "amount_cents": 9900,
        "trial_days": 14,
        "features": {
            "instances": -1,
            "storage_gb": 200,
            "bandwidth_gb": 2000,
            "workspaces": -1,
            "deploys_per_day": -1,
            "support": "dedicated",
        },
    },
]

# Usage-based pricing (overage beyond plan limits)
USAGE_RATES = {
    "compute_hour": 0.007,     # per vCPU-hour
    "storage_gb":   0.05,      # per GB per month
    "bandwidth_gb": 0.10,      # per GB over limit
    "deploy":       0.00,      # free (included)
}


# ──────────────────────────────────────────────
#  Plans
# ──────────────────────────────────────────────

async def ensure_plans_seeded():
    """Seed default plans if none exist."""
    existing = await db.fetch_all("billing_plans")
    if existing:
        return
    now = datetime.now(timezone.utc).isoformat()
    for plan in DEFAULT_PLANS:
        await db.insert("billing_plans", {
            "id": f"plan_{token_gen.token_hex(8)}",
            "code": plan["code"],
            "name": plan["name"],
            "description": plan["description"],
            "interval": plan["interval"],
            "amount_cents": plan["amount_cents"],
            "currency": CURRENCY,
            "features": plan["features"],
            "active": True,
            "created_at": now,
        })
    logger.info("Seeded %d default billing plans", len(DEFAULT_PLANS))


async def list_plans(active_only: bool = True) -> list[dict]:
    """List billing plans."""
    await ensure_plans_seeded()
    if active_only:
        return await db.fetch_all("billing_plans", order_by="amount_cents ASC", active=True)
    return await db.fetch_all("billing_plans", order_by="amount_cents ASC")


async def get_plan(plan_code: str) -> dict:
    """Get a single plan by code."""
    await ensure_plans_seeded()
    plan = await db.fetch_one("billing_plans", code=plan_code)
    if not plan:
        raise NotFoundError("Plan", plan_code)
    return plan


# ──────────────────────────────────────────────
#  Subscriptions
# ──────────────────────────────────────────────

async def get_subscription(user_id: str) -> dict | None:
    """Get a user's current active subscription."""
    sub = await db.fetch_one("billing_subscriptions", user_id=user_id, status="active")
    if not sub:
        sub = await db.fetch_one("billing_subscriptions", user_id=user_id, status="trialing")
    return sub


async def create_subscription(user_id: str, plan_code: str, trial: bool = False) -> dict:
    """Subscribe a user to a plan. Handles proration on upgrade/downgrade."""
    plan = await get_plan(plan_code)

    existing = await get_subscription(user_id)
    proration_credit = 0

    if existing:
        if existing["plan_code"] == plan_code:
            raise ConflictError(f"Already subscribed to '{plan_code}'")

        # Calculate proration credit for unused time on old plan
        old_plan = await db.fetch_one("billing_plans", id=existing["plan_id"])
        proration_credit = _calculate_proration(existing, old_plan)

        event_type = (
            BillingEventType.SUBSCRIPTION_UPGRADED.value
            if plan["amount_cents"] > existing["amount_cents"]
            else BillingEventType.SUBSCRIPTION_DOWNGRADED.value
        )

        await db.update("billing_subscriptions", existing["id"], {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Cancelled subscription %s (switching to %s)", existing["id"], plan_code)

        # Issue proration credit note
        if proration_credit > 0:
            await _create_credit_note_internal(
                user_id=user_id,
                total_cents=proration_credit,
                reason=f"Proration credit: switch from {existing['plan_code']} to {plan_code}",
                credit_type="proration",
            )

        await _emit_event(event_type, "subscription", existing["id"], user_id, {
            "old_plan": existing["plan_code"],
            "new_plan": plan_code,
            "proration_credit": proration_credit,
        })

    now = datetime.now(timezone.utc)

    # Determine period
    plan_def = next((p for p in DEFAULT_PLANS if p["code"] == plan_code), None)
    trial_days = plan_def.get("trial_days", 0) if plan_def else 0

    if trial and trial_days > 0 and plan["amount_cents"] > 0:
        status = "trialing"
        period_end = now + timedelta(days=trial_days)
    else:
        status = "active"
        if plan["interval"] == "monthly":
            period_end = now + timedelta(days=30)
        elif plan["interval"] == "yearly":
            period_end = now + timedelta(days=365)
        else:
            period_end = now + timedelta(hours=1)

    sub = {
        "id": f"sub_{token_gen.token_hex(8)}",
        "user_id": user_id,
        "plan_id": plan["id"],
        "plan_code": plan_code,
        "status": status,
        "current_period_start": now.isoformat(),
        "current_period_end": period_end.isoformat(),
        "amount_cents": plan["amount_cents"],
        "currency": CURRENCY,
        "created_at": now.isoformat(),
        "cancelled_at": None,
    }
    await db.insert("billing_subscriptions", sub)

    await _emit_event(
        BillingEventType.SUBSCRIPTION_CREATED.value,
        "subscription", sub["id"], user_id,
        {"plan_code": plan_code, "status": status},
    )

    logger.info("Created subscription %s (plan=%s, user=%s, status=%s)",
                sub["id"], plan_code, user_id, status)
    return sub


def _calculate_proration(subscription: dict, plan: dict | None) -> int:
    """Calculate proration credit for unused time on a plan."""
    if not plan or plan["amount_cents"] == 0:
        return 0

    try:
        period_start = datetime.fromisoformat(subscription["current_period_start"])
        period_end = datetime.fromisoformat(subscription["current_period_end"])
        now = datetime.now(timezone.utc)

        total_days = max((period_end - period_start).days, 1)
        used_days = max((now - period_start).days, 0)
        remaining_days = max(total_days - used_days, 0)

        daily_rate = plan["amount_cents"] / total_days
        credit = int(daily_rate * remaining_days)
        return credit
    except Exception:
        return 0


async def cancel_subscription(user_id: str, reason: str = "") -> dict:
    """Cancel user's active subscription."""
    sub = await get_subscription(user_id)
    if not sub:
        raise NotFoundError("Subscription", user_id)

    now = datetime.now(timezone.utc).isoformat()
    await db.update("billing_subscriptions", sub["id"], {
        "status": "cancelled",
        "cancelled_at": now,
    })

    await _emit_event(
        BillingEventType.SUBSCRIPTION_CANCELLED.value,
        "subscription", sub["id"], user_id,
        {"reason": reason, "plan_code": sub["plan_code"]},
    )

    logger.info("Cancelled subscription %s for user %s", sub["id"], user_id)
    sub["status"] = "cancelled"
    sub["cancelled_at"] = now
    return sub


async def pause_subscription(user_id: str) -> dict:
    """Pause user's active subscription."""
    sub = await get_subscription(user_id)
    if not sub:
        raise NotFoundError("Subscription", user_id)
    if sub["status"] != "active":
        raise ValidationError("Can only pause active subscriptions")

    now = datetime.now(timezone.utc).isoformat()
    await db.update("billing_subscriptions", sub["id"], {"status": "paused"})
    sub["status"] = "paused"
    return sub


async def resume_subscription(user_id: str) -> dict:
    """Resume a paused subscription."""
    sub = await db.fetch_one("billing_subscriptions", user_id=user_id, status="paused")
    if not sub:
        raise NotFoundError("Subscription", user_id)

    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)
    await db.update("billing_subscriptions", sub["id"], {
        "status": "active",
        "current_period_start": now.isoformat(),
        "current_period_end": period_end.isoformat(),
    })
    sub["status"] = "active"
    return sub


# ──────────────────────────────────────────────
#  Billable Metrics
# ──────────────────────────────────────────────

async def create_billable_metric(
    code: str, name: str, aggregation_type: str = "sum",
    description: str = "", field_name: str = "",
    recurring: bool = False, filters: list | None = None,
) -> dict:
    """Create a billable metric definition (Lago-style)."""
    existing = await db.fetch_one("billing_billable_metrics", code=code)
    if existing:
        raise ConflictError(f"Metric '{code}' already exists")

    if aggregation_type not in [a.value for a in AggregationType]:
        raise ValidationError(f"Invalid aggregation type: {aggregation_type}")

    metric = {
        "id": f"bm_{token_gen.token_hex(8)}",
        "code": code,
        "name": name,
        "description": description,
        "aggregation_type": aggregation_type,
        "field_name": field_name,
        "recurring": recurring,
        "filters": filters or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("billing_billable_metrics", metric)
    logger.info("Created billable metric %s (%s, agg=%s)", code, name, aggregation_type)
    return metric


async def list_billable_metrics() -> list[dict]:
    """List all billable metrics."""
    return await db.fetch_all("billing_billable_metrics", order_by="code ASC")


async def get_billable_metric(code: str) -> dict:
    """Get a billable metric by code."""
    m = await db.fetch_one("billing_billable_metrics", code=code)
    if not m:
        raise NotFoundError("BillableMetric", code)
    return m


async def update_billable_metric(code: str, updates: dict) -> dict:
    """Update a billable metric."""
    m = await get_billable_metric(code)
    allowed = {"name", "description", "field_name", "recurring", "filters"}
    data = {k: v for k, v in updates.items() if k in allowed}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.update("billing_billable_metrics", m["id"], data)
    m.update(data)
    return m


async def delete_billable_metric(code: str):
    """Delete a billable metric."""
    m = await get_billable_metric(code)
    await db.delete("billing_billable_metrics", m["id"])


# ──────────────────────────────────────────────
#  Usage Events (with billable metric aggregation)
# ──────────────────────────────────────────────

async def record_usage(
    user_id: str, metric: str, units: float,
    properties: dict | None = None, transaction_id: str | None = None,
) -> str:
    """Record a usage event. Idempotent when transaction_id provided."""
    # Idempotency check
    if transaction_id:
        existing = await db.fetch_one("billing_usage_events", transaction_id=transaction_id)
        if existing:
            return existing["id"]

    event_id = f"evt_{token_gen.token_hex(10)}"
    await db.insert("billing_usage_events", {
        "id": event_id,
        "user_id": user_id,
        "metric": metric,
        "units": units,
        "transaction_id": transaction_id or "",
        "properties": properties or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    await _emit_event(
        BillingEventType.USAGE_RECORDED.value,
        "usage_event", event_id, user_id,
        {"metric": metric, "units": units},
    )
    return event_id


async def get_usage_summary(
    user_id: str, period_start: str, period_end: str,
) -> dict[str, float]:
    """Aggregate usage events for a billing period using metric definitions."""
    d = await db.get_db()

    # Fetch all defined metrics
    metrics = await list_billable_metrics()
    metric_map = {m["code"]: m for m in metrics}

    # Get raw usage events
    cursor = await d.execute(
        """SELECT metric, units, properties
           FROM billing_usage_events
           WHERE user_id = ? AND created_at >= ? AND created_at < ?
           ORDER BY created_at ASC""",
        (user_id, period_start, period_end),
    )
    rows = await cursor.fetchall()

    # Group by metric
    grouped: dict[str, list] = {}
    for row in rows:
        m = row[0]
        if m not in grouped:
            grouped[m] = []
        grouped[m].append({"units": row[1], "properties": row[2]})

    result: dict[str, float] = {}
    for metric_code, events in grouped.items():
        defn = metric_map.get(metric_code)
        agg = defn["aggregation_type"] if defn else "sum"

        if agg == "count":
            result[metric_code] = len(events)
        elif agg == "sum":
            result[metric_code] = sum(e["units"] for e in events)
        elif agg == "max":
            result[metric_code] = max(e["units"] for e in events) if events else 0
        elif agg == "latest":
            result[metric_code] = events[-1]["units"] if events else 0
        elif agg == "weighted_sum":
            result[metric_code] = sum(e["units"] for e in events)
        elif agg == "count_distinct":
            # Count distinct values of field_name in properties
            field = defn.get("field_name", "") if defn else ""
            if field:
                import json
                distinct = set()
                for e in events:
                    props = e["properties"]
                    if isinstance(props, str):
                        try:
                            props = json.loads(props)
                        except Exception:
                            props = {}
                    distinct.add(props.get(field, ""))
                result[metric_code] = len(distinct)
            else:
                result[metric_code] = len(events)
        else:
            result[metric_code] = sum(e["units"] for e in events)

    # Also include metrics not in billable_metrics (legacy direct usage)
    fallback = await d.execute(
        """SELECT metric, SUM(units) as total
           FROM billing_usage_events
           WHERE user_id = ? AND created_at >= ? AND created_at < ?
           AND metric NOT IN (SELECT code FROM billing_billable_metrics)
           GROUP BY metric""",
        (user_id, period_start, period_end),
    )
    for row in await fallback.fetchall():
        if row[0] not in result:
            result[row[0]] = row[1]

    return result


# ──────────────────────────────────────────────
#  Coupons
# ──────────────────────────────────────────────

async def create_coupon(
    code: str, name: str, coupon_type: str = "percentage",
    value: int = 0, currency: str = "USD",
    frequency: str = "once", frequency_duration: int = 0,
    plan_codes: list[str] | None = None,
    max_redemptions: int = 0, expires_at: str | None = None,
) -> dict:
    """Create a coupon/discount code."""
    existing = await db.fetch_one("billing_coupons", code=code)
    if existing:
        raise ConflictError(f"Coupon code '{code}' already exists")

    if coupon_type not in ("percentage", "fixed_amount"):
        raise ValidationError("coupon_type must be 'percentage' or 'fixed_amount'")
    if coupon_type == "percentage" and (value < 1 or value > 100):
        raise ValidationError("Percentage value must be 1-100")
    if frequency not in ("once", "recurring", "forever"):
        raise ValidationError("frequency must be 'once', 'recurring', or 'forever'")

    coupon = {
        "id": f"cpn_{token_gen.token_hex(8)}",
        "code": code.upper(),
        "name": name,
        "description": "",
        "coupon_type": coupon_type,
        "value": value,
        "currency": currency,
        "frequency": frequency,
        "frequency_duration": frequency_duration,
        "plan_codes": plan_codes or [],
        "max_redemptions": max_redemptions,
        "redemptions_count": 0,
        "amount_cents_remaining": value if coupon_type == "fixed_amount" else 0,
        "expires_at": expires_at,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("billing_coupons", coupon)
    logger.info("Created coupon %s (type=%s, value=%d)", code, coupon_type, value)
    return coupon


async def list_coupons(active_only: bool = True) -> list[dict]:
    """List coupons."""
    if active_only:
        return await db.fetch_all("billing_coupons", active=True)
    return await db.fetch_all("billing_coupons")


async def get_coupon(code: str) -> dict:
    """Get a coupon by code."""
    coupon = await db.fetch_one("billing_coupons", code=code.upper())
    if not coupon:
        raise NotFoundError("Coupon", code)
    return coupon


async def deactivate_coupon(code: str) -> dict:
    """Deactivate a coupon."""
    coupon = await get_coupon(code)
    await db.update("billing_coupons", coupon["id"], {"active": False})
    coupon["active"] = False
    return coupon


async def apply_coupon(user_id: str, coupon_code: str, subscription_id: str | None = None) -> dict:
    """Apply a coupon to a user's subscription."""
    coupon = await get_coupon(coupon_code)

    if not coupon["active"]:
        raise ValidationError("This coupon is no longer active")

    # Check expiration
    if coupon["expires_at"]:
        exp = datetime.fromisoformat(coupon["expires_at"])
        if datetime.now(timezone.utc) > exp:
            raise ValidationError("This coupon has expired")

    # Check max redemptions
    if coupon["max_redemptions"] > 0 and coupon["redemptions_count"] >= coupon["max_redemptions"]:
        raise ValidationError("This coupon has reached its maximum redemptions")

    # Check plan restriction
    if coupon["plan_codes"] and subscription_id:
        sub = await db.fetch_one("billing_subscriptions", id=subscription_id)
        if sub and sub["plan_code"] not in coupon["plan_codes"]:
            raise ValidationError(f"This coupon is not valid for your current plan")

    # Check if already applied
    existing = await db.fetch_one(
        "billing_applied_coupons", user_id=user_id, coupon_id=coupon["id"], status="active",
    )
    if existing:
        raise ConflictError("Coupon is already applied to your account")

    # Determine periods
    periods = 0
    if coupon["frequency"] == "once":
        periods = 1
    elif coupon["frequency"] == "recurring":
        periods = coupon["frequency_duration"] if coupon["frequency_duration"] > 0 else 12
    # forever = 0 (no limit)

    applied = {
        "id": f"ac_{token_gen.token_hex(8)}",
        "user_id": user_id,
        "coupon_id": coupon["id"],
        "subscription_id": subscription_id or "",
        "status": "active",
        "amount_cents_used": 0,
        "periods_remaining": periods,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": coupon["expires_at"],
    }
    await db.insert("billing_applied_coupons", applied)

    # Increment redemptions
    await db.update("billing_coupons", coupon["id"], {
        "redemptions_count": coupon["redemptions_count"] + 1,
    })

    await _emit_event(
        BillingEventType.COUPON_APPLIED.value,
        "coupon", coupon["id"], user_id,
        {"code": coupon_code, "coupon_type": coupon["coupon_type"], "value": coupon["value"]},
    )

    logger.info("Applied coupon %s to user %s", coupon_code, user_id)
    return applied


async def remove_applied_coupon(user_id: str, applied_coupon_id: str):
    """Remove an applied coupon from user."""
    ac = await db.fetch_one("billing_applied_coupons", id=applied_coupon_id, user_id=user_id)
    if not ac:
        raise NotFoundError("AppliedCoupon", applied_coupon_id)
    await db.update("billing_applied_coupons", applied_coupon_id, {"status": "terminated"})

    await _emit_event(
        BillingEventType.COUPON_REMOVED.value,
        "coupon", ac["coupon_id"], user_id, {},
    )


async def list_applied_coupons(user_id: str) -> list[dict]:
    """List user's active applied coupons."""
    return await db.fetch_all("billing_applied_coupons", order_by="applied_at DESC", user_id=user_id, status="active")


async def _calculate_coupon_discount(user_id: str, subtotal_cents: int) -> tuple[int, list[dict]]:
    """Calculate total coupon discount for an invoice. Returns (discount_cents, applied_list)."""
    applied = await list_applied_coupons(user_id)
    total_discount = 0
    applied_details = []

    for ac in applied:
        coupon = await db.fetch_one("billing_coupons", id=ac["coupon_id"])
        if not coupon or not coupon["active"]:
            continue

        if coupon["coupon_type"] == "percentage":
            discount = int(subtotal_cents * coupon["value"] / 100)
        else:
            discount = min(coupon["value"], subtotal_cents - total_discount)

        if discount <= 0:
            continue

        total_discount += discount
        applied_details.append({
            "coupon_code": coupon["code"],
            "coupon_name": coupon["name"],
            "discount_cents": discount,
        })

        # Update usage tracking
        await db.update("billing_applied_coupons", ac["id"], {
            "amount_cents_used": ac["amount_cents_used"] + discount,
        })

        # Decrement periods for once/recurring
        if coupon["frequency"] in ("once", "recurring"):
            remaining = ac["periods_remaining"] - 1
            if remaining <= 0:
                await db.update("billing_applied_coupons", ac["id"], {
                    "status": "terminated",
                    "periods_remaining": 0,
                })
            else:
                await db.update("billing_applied_coupons", ac["id"], {
                    "periods_remaining": remaining,
                })

    return total_discount, applied_details


# ──────────────────────────────────────────────
#  Credit Notes
# ──────────────────────────────────────────────

async def _create_credit_note_internal(
    user_id: str, total_cents: int, reason: str = "",
    credit_type: str = "refund", invoice_id: str | None = None,
    items: list | None = None,
) -> dict:
    """Internal helper to create credit notes."""
    now = datetime.now(timezone.utc)
    cn_number = f"CN-{now.strftime('%Y%m')}-{token_gen.token_hex(4).upper()}"

    cn = {
        "id": f"cn_{token_gen.token_hex(10)}",
        "user_id": user_id,
        "invoice_id": invoice_id or "",
        "number": cn_number,
        "reason": reason,
        "credit_type": credit_type,
        "status": "available",
        "total_cents": total_cents,
        "balance_cents": total_cents,
        "currency": CURRENCY,
        "items": items or [],
        "refund_status": "pending",
        "created_at": now.isoformat(),
        "voided_at": None,
    }
    await db.insert("billing_credit_notes", cn)

    await _emit_event(
        BillingEventType.CREDIT_NOTE_CREATED.value,
        "credit_note", cn["id"], user_id,
        {"total_cents": total_cents, "reason": reason, "credit_type": credit_type},
    )

    logger.info("Created credit note %s for user %s ($%.2f)",
                cn["id"], user_id, total_cents / 100)
    return cn


async def create_credit_note(
    user_id: str, invoice_id: str | None = None,
    total_cents: int = 0, reason: str = "",
    credit_type: str = "refund", items: list | None = None,
) -> dict:
    """Create a credit note (refund/adjustment) for a user."""
    if total_cents <= 0:
        raise ValidationError("Credit note amount must be positive")

    if invoice_id:
        inv = await db.fetch_one("billing_invoices", id=invoice_id)
        if not inv:
            raise NotFoundError("Invoice", invoice_id)
        if inv["user_id"] != user_id:
            raise ValidationError("Invoice does not belong to this user")

    return await _create_credit_note_internal(
        user_id, total_cents, reason, credit_type, invoice_id, items,
    )


async def list_credit_notes(user_id: str) -> list[dict]:
    """List user's credit notes."""
    return await db.fetch_all("billing_credit_notes", user_id=user_id)


async def get_credit_note(cn_id: str) -> dict:
    """Get a credit note."""
    cn = await db.fetch_one("billing_credit_notes", id=cn_id)
    if not cn:
        raise NotFoundError("CreditNote", cn_id)
    return cn


async def void_credit_note(cn_id: str) -> dict:
    """Void a credit note."""
    cn = await get_credit_note(cn_id)
    if cn["status"] == "voided":
        raise ValidationError("Credit note is already voided")
    if cn["balance_cents"] < cn["total_cents"]:
        raise ValidationError("Cannot void a partially consumed credit note")

    now = datetime.now(timezone.utc).isoformat()
    await db.update("billing_credit_notes", cn_id, {
        "status": "voided",
        "voided_at": now,
    })
    cn["status"] = "voided"
    cn["voided_at"] = now
    return cn


async def _apply_credit_notes(user_id: str, amount_cents: int) -> tuple[int, list[dict]]:
    """Apply available credit notes to reduce an amount. Returns (credits_used, details)."""
    notes = await db.fetch_all("billing_credit_notes", user_id=user_id, status="available")
    total_applied = 0
    details = []

    for cn in notes:
        if total_applied >= amount_cents:
            break
        available = cn["balance_cents"]
        if available <= 0:
            continue

        use = min(available, amount_cents - total_applied)
        total_applied += use
        new_balance = available - use

        status = "consumed" if new_balance == 0 else "available"
        await db.update("billing_credit_notes", cn["id"], {
            "balance_cents": new_balance,
            "status": status,
        })
        details.append({"credit_note_id": cn["id"], "number": cn["number"], "amount_cents": use})

    return total_applied, details


# ──────────────────────────────────────────────
#  Tax Calculation
# ──────────────────────────────────────────────

async def create_tax_rate(
    name: str, code: str, rate: float,
    description: str = "", applied_to: str = "all", region: str = "",
) -> dict:
    """Create a tax rate."""
    existing = await db.fetch_one("billing_taxes", code=code)
    if existing:
        raise ConflictError(f"Tax code '{code}' already exists")

    if rate < 0 or rate > 100:
        raise ValidationError("Tax rate must be between 0 and 100")

    tax = {
        "id": f"tax_{token_gen.token_hex(8)}",
        "name": name,
        "code": code,
        "rate": rate,
        "description": description,
        "applied_to": applied_to,
        "region": region,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("billing_taxes", tax)
    logger.info("Created tax rate %s (%s%%)", name, rate)
    return tax


async def list_tax_rates(active_only: bool = True) -> list[dict]:
    """List tax rates."""
    if active_only:
        return await db.fetch_all("billing_taxes", active=True)
    return await db.fetch_all("billing_taxes")


async def get_tax_rate(code: str) -> dict:
    """Get a tax rate by code."""
    t = await db.fetch_one("billing_taxes", code=code)
    if not t:
        raise NotFoundError("TaxRate", code)
    return t


async def update_tax_rate(code: str, updates: dict) -> dict:
    """Update a tax rate."""
    t = await get_tax_rate(code)
    allowed = {"name", "rate", "description", "applied_to", "region", "active"}
    data = {k: v for k, v in updates.items() if k in allowed}
    await db.update("billing_taxes", t["id"], data)
    t.update(data)
    return t


async def _calculate_taxes(subtotal_cents: int) -> tuple[int, list[dict]]:
    """Calculate applicable taxes on a subtotal. Returns (tax_total, breakdown)."""
    taxes = await list_tax_rates(active_only=True)
    total_tax = 0
    breakdown = []

    for tax in taxes:
        if tax["applied_to"] in ("all", "subscription", "usage"):
            tax_amount = int(subtotal_cents * tax["rate"] / 100)
            total_tax += tax_amount
            breakdown.append({
                "tax_code": tax["code"],
                "tax_name": tax["name"],
                "rate": tax["rate"],
                "amount_cents": tax_amount,
            })

    return total_tax, breakdown


# ──────────────────────────────────────────────
#  Wallets (Lago-style prepaid credits)
# ──────────────────────────────────────────────

async def create_wallet(
    user_id: str, name: str = "Primary",
    paid_credits: float = 0.0, granted_credits: float = 0.0,
    rate_amount: float = 1.0, expiration_at: str | None = None,
) -> dict:
    """Create a wallet for a user. Up to 5 wallets per user."""
    existing = await db.fetch_all("billing_wallets", user_id=user_id, status="active")
    if len(existing) >= 5:
        raise ValidationError("Maximum 5 active wallets per user")

    initial_credits = paid_credits + granted_credits
    balance_cents = int(initial_credits * rate_amount * 100)

    wallet = {
        "id": f"wal_{token_gen.token_hex(8)}",
        "user_id": user_id,
        "name": name,
        "currency": CURRENCY,
        "balance_cents": balance_cents,
        "consumed_cents": 0,
        "rate_amount": rate_amount,
        "credits_balance": initial_credits,
        "credits_consumed": 0.0,
        "status": "active",
        "expiration_at": expiration_at,
        "priority": len(existing),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "depleted_at": None,
    }
    await db.insert("billing_wallets", wallet)

    # Record initial transaction
    if initial_credits > 0:
        await db.insert("billing_wallet_transactions", {
            "id": f"wt_{token_gen.token_hex(8)}",
            "wallet_id": wallet["id"],
            "transaction_type": "inbound",
            "amount": balance_cents / 100,
            "credit_amount": initial_credits,
            "source": "initial",
            "settled_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    await _emit_event(
        BillingEventType.WALLET_CREDITED.value,
        "wallet", wallet["id"], user_id,
        {"credits": initial_credits, "balance_cents": balance_cents},
    )

    logger.info("Created wallet %s for user %s (credits=%.2f)", wallet["id"], user_id, initial_credits)
    return wallet


async def list_wallets(user_id: str) -> list[dict]:
    """List user's wallets."""
    return await db.fetch_all("billing_wallets", user_id=user_id, order_by="priority ASC")


async def get_wallet(wallet_id: str) -> dict:
    """Get a wallet."""
    w = await db.fetch_one("billing_wallets", id=wallet_id)
    if not w:
        raise NotFoundError("Wallet", wallet_id)
    return w


async def top_up_wallet(wallet_id: str, paid_credits: float = 0.0, granted_credits: float = 0.0) -> dict:
    """Add credits to a wallet."""
    wallet = await get_wallet(wallet_id)
    if wallet["status"] != "active":
        raise ValidationError("Wallet is not active")

    credits = paid_credits + granted_credits
    amount_cents = int(credits * wallet["rate_amount"] * 100)

    new_balance = wallet["balance_cents"] + amount_cents
    new_credits = wallet["credits_balance"] + credits

    await db.update("billing_wallets", wallet_id, {
        "balance_cents": new_balance,
        "credits_balance": new_credits,
        "depleted_at": None,
    })

    await db.insert("billing_wallet_transactions", {
        "id": f"wt_{token_gen.token_hex(8)}",
        "wallet_id": wallet_id,
        "transaction_type": "inbound",
        "amount": amount_cents / 100,
        "credit_amount": credits,
        "source": "topup",
        "settled_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    await _emit_event(
        BillingEventType.WALLET_CREDITED.value,
        "wallet", wallet_id, wallet["user_id"],
        {"credits": credits, "balance_cents": new_balance},
    )

    wallet["balance_cents"] = new_balance
    wallet["credits_balance"] = new_credits
    return wallet


async def get_wallet_transactions(wallet_id: str) -> list[dict]:
    """List transactions for a wallet."""
    return await db.fetch_all("billing_wallet_transactions", wallet_id=wallet_id)


async def _debit_wallets(user_id: str, amount_cents: int) -> tuple[int, list[dict]]:
    """Debit from user's wallets in priority order. Returns (debited, details)."""
    wallets = await db.fetch_all("billing_wallets", user_id=user_id, status="active", order_by="priority ASC")
    total_debited = 0
    details = []

    for wallet in wallets:
        if total_debited >= amount_cents:
            break
        # Check expiration
        if wallet.get("expiration_at"):
            exp = datetime.fromisoformat(wallet["expiration_at"])
            if datetime.now(timezone.utc) > exp:
                await db.update("billing_wallets", wallet["id"], {"status": "terminated"})
                continue

        available = wallet["balance_cents"]
        if available <= 0:
            continue

        debit = min(available, amount_cents - total_debited)
        total_debited += debit

        new_balance = available - debit
        new_consumed = wallet["consumed_cents"] + debit
        credit_debit = debit / (wallet["rate_amount"] * 100) if wallet["rate_amount"] > 0 else 0

        updates: dict = {
            "balance_cents": new_balance,
            "consumed_cents": new_consumed,
            "credits_consumed": wallet["credits_consumed"] + credit_debit,
            "credits_balance": wallet["credits_balance"] - credit_debit,
        }
        if new_balance == 0:
            updates["depleted_at"] = datetime.now(timezone.utc).isoformat()

        await db.update("billing_wallets", wallet["id"], updates)

        await db.insert("billing_wallet_transactions", {
            "id": f"wt_{token_gen.token_hex(8)}",
            "wallet_id": wallet["id"],
            "transaction_type": "outbound",
            "amount": debit / 100,
            "credit_amount": credit_debit,
            "source": "invoice_deduction",
            "settled_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        details.append({
            "wallet_id": wallet["id"],
            "wallet_name": wallet["name"],
            "amount_cents": debit,
        })

    return total_debited, details


# ──────────────────────────────────────────────
#  Invoices (with coupons, credit notes, taxes)
# ──────────────────────────────────────────────

async def generate_invoice(user_id: str, subscription_id: str | None = None) -> dict:
    """Generate a draft invoice for a user.
    Includes: subscription + usage + coupons + credit notes + taxes."""
    now = datetime.now(timezone.utc)
    inv_id = f"inv_{token_gen.token_hex(10)}"
    inv_number = f"INV-{now.strftime('%Y%m')}-{token_gen.token_hex(4).upper()}"

    items: list[dict] = []
    total_cents = 0

    # 1) Subscription line item
    sub = await get_subscription(user_id) if not subscription_id else await db.fetch_one(
        "billing_subscriptions", id=subscription_id
    )
    if sub and sub["amount_cents"] > 0:
        plan = await db.fetch_one("billing_plans", id=sub["plan_id"])
        item = {
            "id": f"ii_{token_gen.token_hex(8)}",
            "invoice_id": inv_id,
            "type": "subscription",
            "description": f"{plan['name']} plan — {plan['interval']}",
            "units": 1,
            "unit_price_cents": sub["amount_cents"],
            "amount_cents": sub["amount_cents"],
            "metric": None,
        }
        items.append(item)
        total_cents += sub["amount_cents"]

    # 2) Usage line items (overage)
    if sub:
        plan = await db.fetch_one("billing_plans", id=sub["plan_id"])
        usage = await get_usage_summary(
            user_id, sub["current_period_start"], now.isoformat()
        )
        features = plan.get("features", {})
        for metric, total_units in usage.items():
            rate = USAGE_RATES.get(metric, 0)
            if rate <= 0:
                continue
            limit_key = metric.replace("_hour", "s").replace("_gb", "_gb")
            plan_limit = features.get(limit_key, 0)
            if plan_limit == -1:
                continue  # unlimited
            overage = max(0, total_units - plan_limit) if plan_limit > 0 else total_units
            if overage <= 0:
                continue
            overage_cents = int(overage * rate * 100)
            item = {
                "id": f"ii_{token_gen.token_hex(8)}",
                "invoice_id": inv_id,
                "type": "usage",
                "description": f"{metric} overage ({overage:.2f} units @ ${rate}/unit)",
                "units": overage,
                "unit_price_cents": int(rate * 100),
                "amount_cents": overage_cents,
                "metric": metric,
            }
            items.append(item)
            total_cents += overage_cents

    subtotal_cents = total_cents

    # 3) Apply coupon discounts
    discount_cents, coupon_details = await _calculate_coupon_discount(user_id, subtotal_cents)
    if discount_cents > 0:
        items.append({
            "id": f"ii_{token_gen.token_hex(8)}",
            "invoice_id": inv_id,
            "type": "discount",
            "description": f"Coupon discount ({', '.join(d['coupon_code'] for d in coupon_details)})",
            "units": 1,
            "unit_price_cents": -discount_cents,
            "amount_cents": -discount_cents,
            "metric": None,
        })
        total_cents -= discount_cents

    # 4) Calculate taxes
    tax_cents, tax_breakdown = await _calculate_taxes(max(total_cents, 0))
    if tax_cents > 0:
        for tb in tax_breakdown:
            items.append({
                "id": f"ii_{token_gen.token_hex(8)}",
                "invoice_id": inv_id,
                "type": "tax",
                "description": f"{tb['tax_name']} ({tb['rate']}%)",
                "units": 1,
                "unit_price_cents": tb["amount_cents"],
                "amount_cents": tb["amount_cents"],
                "metric": None,
            })
        total_cents += tax_cents

    total_cents = max(total_cents, 0)

    # Create invoice
    invoice = {
        "id": inv_id,
        "user_id": user_id,
        "subscription_id": sub["id"] if sub else None,
        "number": inv_number,
        "status": "draft",
        "payment_status": "pending",
        "currency": CURRENCY,
        "subtotal_cents": subtotal_cents,
        "credits_applied_cents": 0,
        "total_cents": total_cents,
        "period_start": sub["current_period_start"] if sub else now.isoformat(),
        "period_end": sub["current_period_end"] if sub else now.isoformat(),
        "due_date": (now + timedelta(days=GRACE_PERIOD_DAYS)).isoformat(),
        "finalized_at": None,
        "paid_at": None,
        "created_at": now.isoformat(),
    }
    await db.insert("billing_invoices", invoice)

    for item in items:
        await db.insert("billing_invoice_items", item)

    await _emit_event(
        BillingEventType.INVOICE_GENERATED.value,
        "invoice", inv_id, user_id,
        {"total_cents": total_cents, "items_count": len(items)},
    )

    logger.info("Generated invoice %s for user %s (subtotal=$%.2f, discount=$%.2f, tax=$%.2f, total=$%.2f)",
                inv_id, user_id, subtotal_cents / 100, discount_cents / 100,
                tax_cents / 100, total_cents / 100)
    return {**invoice, "items": items, "coupon_details": coupon_details, "tax_breakdown": tax_breakdown}


async def finalize_invoice(invoice_id: str) -> dict:
    """Finalize a draft invoice — makes it immutable, applies credits + wallets, triggers payment."""
    inv = await db.fetch_one("billing_invoices", id=invoice_id)
    if not inv:
        raise NotFoundError("Invoice", invoice_id)
    if inv["status"] != "draft":
        raise ValidationError(f"Invoice is already {inv['status']}")

    now = datetime.now(timezone.utc).isoformat()
    remaining = inv["total_cents"]
    total_credits = 0

    # 1) Apply credit notes
    cn_used, cn_details = await _apply_credit_notes(inv["user_id"], remaining)
    if cn_used > 0:
        remaining -= cn_used
        total_credits += cn_used

    # 2) Apply wallets (Lago-style)
    if remaining > 0:
        wallet_used, wallet_details = await _debit_wallets(inv["user_id"], remaining)
        if wallet_used > 0:
            remaining -= wallet_used
            total_credits += wallet_used

    # 3) Legacy wallet (users.balance)
    if remaining > 0:
        user = await db.fetch_one("users", id=inv["user_id"])
        if user and user["balance"] > 0:
            balance_cents = int(user["balance"] * 100)
            from_balance = min(balance_cents, remaining)
            remaining -= from_balance
            total_credits += from_balance
            new_balance = (balance_cents - from_balance) / 100
            await db.update("users", user["id"], {"balance": new_balance})

            if from_balance > 0:
                await db.insert("transactions", {
                    "id": f"txn_{token_gen.token_hex(12)}",
                    "user_id": inv["user_id"],
                    "type": "charge",
                    "amount": -(from_balance / 100),
                    "description": f"Invoice {inv['number']}",
                    "reference": invoice_id,
                })

    payment_status = "succeeded" if remaining == 0 else "pending"
    await db.update("billing_invoices", invoice_id, {
        "status": "finalized",
        "credits_applied_cents": total_credits,
        "total_cents": remaining,
        "payment_status": payment_status,
        "finalized_at": now,
        "paid_at": now if payment_status == "succeeded" else None,
    })

    event_type = (BillingEventType.INVOICE_PAID.value
                  if payment_status == "succeeded"
                  else BillingEventType.INVOICE_FINALIZED.value)
    await _emit_event(
        event_type, "invoice", invoice_id, inv["user_id"],
        {"credits_applied": total_credits, "remaining": remaining, "payment_status": payment_status},
    )

    logger.info("Finalized invoice %s (credits=%d, remaining=%d, status=%s)",
                invoice_id, total_credits, remaining, payment_status)

    inv["status"] = "finalized"
    inv["credits_applied_cents"] = total_credits
    inv["total_cents"] = remaining
    inv["payment_status"] = payment_status
    return inv


async def list_invoices(user_id: str) -> list[dict]:
    """List all invoices for a user."""
    invoices = await db.fetch_all("billing_invoices", user_id=user_id)
    for inv in invoices:
        d = await db.get_db()
        cursor = await d.execute(
            "SELECT * FROM billing_invoice_items WHERE invoice_id = ?",
            (inv["id"],),
        )
        rows = await cursor.fetchall()
        inv["items"] = [db._row_to_dict(r) for r in rows]
    return invoices


async def get_invoice(invoice_id: str) -> dict:
    """Get a single invoice with items."""
    inv = await db.fetch_one("billing_invoices", id=invoice_id)
    if not inv:
        raise NotFoundError("Invoice", invoice_id)
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM billing_invoice_items WHERE invoice_id = ?",
        (inv["id"],),
    )
    rows = await cursor.fetchall()
    inv["items"] = [db._row_to_dict(r) for r in rows]
    return inv


async def void_invoice(invoice_id: str) -> dict:
    """Void an invoice (only if not paid)."""
    inv = await db.fetch_one("billing_invoices", id=invoice_id)
    if not inv:
        raise NotFoundError("Invoice", invoice_id)
    if inv["payment_status"] == "succeeded":
        raise ValidationError("Cannot void a paid invoice")

    await db.update("billing_invoices", invoice_id, {
        "status": "void",
        "payment_status": "void",
    })

    await _emit_event(
        BillingEventType.INVOICE_VOIDED.value,
        "invoice", invoice_id, inv["user_id"], {},
    )

    logger.info("Voided invoice %s", invoice_id)
    inv["status"] = "void"
    return inv


# ──────────────────────────────────────────────
#  Payment Methods
# ──────────────────────────────────────────────

async def add_payment_method(
    user_id: str, method_type: str, provider: str,
    provider_id: str, label: str, is_default: bool = False,
    metadata: dict | None = None,
) -> dict:
    """Register a payment method for a user."""
    pm_id = f"pm_{token_gen.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()

    if is_default:
        d = await db.get_db()
        await d.execute(
            "UPDATE billing_payment_methods SET is_default = 0 WHERE user_id = ?",
            (user_id,),
        )
        await d.commit()

    pm = {
        "id": pm_id,
        "user_id": user_id,
        "type": method_type,
        "provider": provider,
        "provider_id": provider_id,
        "label": label,
        "is_default": is_default,
        "metadata": metadata or {},
        "created_at": now,
    }
    await db.insert("billing_payment_methods", pm)
    logger.info("Added payment method %s (type=%s) for user %s", pm_id, method_type, user_id)
    return pm


async def list_payment_methods(user_id: str) -> list[dict]:
    """List user's payment methods."""
    return await db.fetch_all("billing_payment_methods", user_id=user_id)


async def remove_payment_method(pm_id: str, user_id: str):
    """Remove a payment method."""
    pm = await db.fetch_one("billing_payment_methods", id=pm_id, user_id=user_id)
    if not pm:
        raise NotFoundError("PaymentMethod", pm_id)
    await db.delete("billing_payment_methods", pm_id)
    logger.info("Removed payment method %s", pm_id)


async def set_default_payment_method(pm_id: str, user_id: str) -> dict:
    """Set a payment method as default."""
    pm = await db.fetch_one("billing_payment_methods", id=pm_id, user_id=user_id)
    if not pm:
        raise NotFoundError("PaymentMethod", pm_id)
    d = await db.get_db()
    await d.execute(
        "UPDATE billing_payment_methods SET is_default = 0 WHERE user_id = ?",
        (user_id,),
    )
    await d.execute(
        "UPDATE billing_payment_methods SET is_default = 1 WHERE id = ?",
        (pm_id,),
    )
    await d.commit()
    pm["is_default"] = True
    return pm


# ──────────────────────────────────────────────
#  Stripe Integration
# ──────────────────────────────────────────────

async def create_checkout_session(
    user_id: str, plan_code: str, success_url: str, cancel_url: str,
    payment_methods: list[str] | None = None,
) -> dict:
    """Create a Stripe checkout session for a plan subscription.
    Supports card + google_pay + apple_pay via payment_method_types.
    """
    import os
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise ValidationError("Stripe is not configured. Set STRIPE_SECRET_KEY.")

    plan = await get_plan(plan_code)
    if plan["amount_cents"] == 0:
        sub = await create_subscription(user_id, plan_code)
        return {"subscription": sub, "free": True}

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    # Default to card + Google Pay + Apple Pay (Link)
    pm_types = payment_methods or ["card"]

    import httpx
    data: dict[str, str] = {
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(plan["amount_cents"]),
        "line_items[0][price_data][recurring][interval]": plan["interval"],
        "line_items[0][price_data][product_data][name]": f"NSO {plan['name']} Plan",
        "line_items[0][price_data][product_data][description]": plan["description"],
        "line_items[0][quantity]": "1",
        "customer_email": user["email"],
        "client_reference_id": user_id,
        "metadata[plan_code]": plan_code,
        "metadata[user_id]": user_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }

    for i, pm_type in enumerate(pm_types):
        data[f"payment_method_types[{i}]"] = pm_type

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(stripe_key, ""),
            data=data,
        )

    if resp.status_code != 200:
        logger.error("Stripe checkout error: %s", resp.text)
        raise ValidationError("Failed to create Stripe checkout session")

    session = resp.json()
    logger.info("Created Stripe checkout session %s for user %s (plan=%s)",
                session.get("id"), user_id, plan_code)
    return {
        "session_id": session["id"],
        "url": session.get("url"),
        "plan_code": plan_code,
    }


async def create_topup_checkout(
    user_id: str, amount_cents: int, success_url: str, cancel_url: str,
    payment_methods: list[str] | None = None,
) -> dict:
    """Create a Stripe checkout session for wallet top-up.
    Supports card + Google Pay.
    """
    import os
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise ValidationError("Stripe is not configured. Set STRIPE_SECRET_KEY.")

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    pm_types = payment_methods or ["card"]

    import httpx
    data: dict[str, str] = {
        "mode": "payment",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": "NSO Wallet Top-Up",
        "line_items[0][quantity]": "1",
        "customer_email": user["email"],
        "client_reference_id": user_id,
        "metadata[type]": "topup",
        "metadata[user_id]": user_id,
        "metadata[amount_cents]": str(amount_cents),
        "success_url": success_url,
        "cancel_url": cancel_url,
    }

    for i, pm_type in enumerate(pm_types):
        data[f"payment_method_types[{i}]"] = pm_type

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(stripe_key, ""),
            data=data,
        )

    if resp.status_code != 200:
        logger.error("Stripe topup error: %s", resp.text)
        raise ValidationError("Failed to create Stripe checkout session")

    session = resp.json()
    return {
        "session_id": session["id"],
        "url": session.get("url"),
        "amount_cents": amount_cents,
    }


async def handle_stripe_webhook(payload: dict) -> dict:
    """Process Stripe webhook events.
    Called by the webhook endpoint after signature verification.
    """
    event_type = payload.get("type", "")
    data = payload.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")

        if metadata.get("type") == "topup":
            amount_cents = int(metadata.get("amount_cents", 0))
            amount = amount_cents / 100
            user = await db.fetch_one("users", id=user_id)
            if user:
                new_balance = user["balance"] + amount
                await db.update("users", user_id, {"balance": new_balance})
                await db.insert("transactions", {
                    "id": f"txn_{token_gen.token_hex(12)}",
                    "user_id": user_id,
                    "type": "topup",
                    "amount": amount,
                    "description": f"Stripe top-up: ${amount:.2f}",
                    "reference": data.get("id", ""),
                })
                await _emit_event(
                    BillingEventType.PAYMENT_SUCCEEDED.value,
                    "topup", data.get("id", ""), user_id,
                    {"amount_cents": amount_cents},
                )
                logger.info("Stripe top-up completed: user=%s amount=$%.2f", user_id, amount)
            return {"handled": True, "type": "topup"}

        else:
            plan_code = metadata.get("plan_code")
            if user_id and plan_code:
                sub = await create_subscription(user_id, plan_code)

                stripe_customer = data.get("customer")
                if stripe_customer:
                    await add_payment_method(
                        user_id, "card", "stripe",
                        stripe_customer, "Stripe Card",
                        is_default=True,
                    )

                # Check for Google Pay / Apple Pay payment method
                pm_type = data.get("payment_method_types", ["card"])
                if isinstance(pm_type, list) and len(pm_type) > 0:
                    actual_type = pm_type[0]
                    if actual_type in ("google_pay", "apple_pay"):
                        await add_payment_method(
                            user_id, actual_type, "stripe",
                            stripe_customer or "", f"Stripe {actual_type.replace('_', ' ').title()}",
                        )

                await _emit_event(
                    BillingEventType.PAYMENT_SUCCEEDED.value,
                    "subscription", sub["id"], user_id,
                    {"plan_code": plan_code},
                )
                logger.info("Stripe subscription activated: user=%s plan=%s", user_id, plan_code)
                return {"handled": True, "type": "subscription", "subscription_id": sub["id"]}

    elif event_type == "invoice.payment_succeeded":
        stripe_sub = data.get("subscription")
        if stripe_sub:
            await _emit_event(
                BillingEventType.PAYMENT_SUCCEEDED.value,
                "stripe_invoice", data.get("id", ""), "",
                {"stripe_subscription": stripe_sub},
            )
            logger.info("Stripe payment succeeded for subscription %s", stripe_sub)
            return {"handled": True, "type": "payment_succeeded"}

    elif event_type == "invoice.payment_failed":
        stripe_sub = data.get("subscription")
        if stripe_sub:
            await _emit_event(
                BillingEventType.PAYMENT_FAILED.value,
                "stripe_invoice", data.get("id", ""), "",
                {"stripe_subscription": stripe_sub},
            )
            logger.warning("Stripe payment failed for subscription %s", stripe_sub)
            return {"handled": True, "type": "payment_failed"}

    elif event_type == "customer.subscription.deleted":
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        if user_id:
            try:
                await cancel_subscription(user_id)
            except Exception:
                pass
            return {"handled": True, "type": "subscription_cancelled"}

    return {"handled": False, "type": event_type}


# ──────────────────────────────────────────────
#  Billing overview (for dashboard)
# ──────────────────────────────────────────────

async def get_billing_overview(user_id: str) -> dict:
    """Get a complete billing overview for the dashboard."""
    user = await db.fetch_one("users", id=user_id)
    sub = await get_subscription(user_id)
    plan = None
    if sub:
        plan = await db.fetch_one("billing_plans", id=sub["plan_id"])

    invoices = await db.fetch_all("billing_invoices", user_id=user_id)
    payment_methods = await list_payment_methods(user_id)
    transactions = await db.fetch_all("transactions", user_id=user_id)
    coupons = await list_applied_coupons(user_id)
    credit_notes = await list_credit_notes(user_id)
    wallets = await list_wallets(user_id)

    # Current period usage
    usage = {}
    if sub:
        usage = await get_usage_summary(
            user_id, sub["current_period_start"],
            datetime.now(timezone.utc).isoformat(),
        )

    # Available credit notes balance
    cn_balance = sum(cn["balance_cents"] for cn in credit_notes if cn["status"] == "available")

    # Total wallet balance
    wallet_balance = sum(w["balance_cents"] for w in wallets if w["status"] == "active")

    return {
        "balance": user["balance"] if user else 0,
        "currency": CURRENCY,
        "plan": plan,
        "subscription": sub,
        "invoices": invoices[:10],
        "payment_methods": payment_methods,
        "transactions": transactions[:20],
        "usage": usage,
        "applied_coupons": coupons,
        "credit_notes": credit_notes[:10],
        "credit_notes_balance_cents": cn_balance,
        "wallets": wallets,
        "wallet_balance_cents": wallet_balance,
    }
