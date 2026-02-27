"""
nso-billing — Core billing engine.

Inspired by Lago (event-based metering) and BoxBilling (hosting lifecycle).
Handles: plans, subscriptions, usage events, invoicing, wallet credits,
payment method management, and Stripe integration.
"""
import logging
import secrets as token_gen
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

from core import db
from core.errors import NotFoundError, ConflictError, ValidationError

logger = logging.getLogger("setupo.billing")


# ──────────────────────────────────────────────
#  Constants
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


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"
    VOID = "void"


class PaymentMethodType(str, Enum):
    CARD = "card"
    GOOGLE_PAY = "google_pay"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"


CURRENCY = "USD"
GRACE_PERIOD_DAYS = 3


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
    return await db.fetch_one("billing_subscriptions", user_id=user_id, status="active")


async def create_subscription(user_id: str, plan_code: str) -> dict:
    """Subscribe a user to a plan. Cancels any existing active subscription."""
    plan = await get_plan(plan_code)

    existing = await get_subscription(user_id)
    if existing:
        if existing["plan_code"] == plan_code:
            raise ConflictError(f"Already subscribed to '{plan_code}'")
        # Cancel old subscription, start new one
        await db.update("billing_subscriptions", existing["id"], {
            "status": "cancelled",
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Cancelled subscription %s (upgrade to %s)", existing["id"], plan_code)

    now = datetime.now(timezone.utc)
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
        "status": "active",
        "current_period_start": now.isoformat(),
        "current_period_end": period_end.isoformat(),
        "amount_cents": plan["amount_cents"],
        "currency": CURRENCY,
        "created_at": now.isoformat(),
        "cancelled_at": None,
    }
    await db.insert("billing_subscriptions", sub)
    logger.info("Created subscription %s (plan=%s, user=%s)", sub["id"], plan_code, user_id)
    return sub


async def cancel_subscription(user_id: str) -> dict:
    """Cancel user's active subscription."""
    sub = await get_subscription(user_id)
    if not sub:
        raise NotFoundError("Subscription", user_id)

    now = datetime.now(timezone.utc).isoformat()
    await db.update("billing_subscriptions", sub["id"], {
        "status": "cancelled",
        "cancelled_at": now,
    })
    logger.info("Cancelled subscription %s for user %s", sub["id"], user_id)
    sub["status"] = "cancelled"
    sub["cancelled_at"] = now
    return sub


# ──────────────────────────────────────────────
#  Usage Events
# ──────────────────────────────────────────────

async def record_usage(user_id: str, metric: str, units: float, properties: dict | None = None) -> str:
    """Record a usage event for billing."""
    event_id = f"evt_{token_gen.token_hex(10)}"
    await db.insert("billing_usage_events", {
        "id": event_id,
        "user_id": user_id,
        "metric": metric,
        "units": units,
        "properties": properties or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return event_id


async def get_usage_summary(user_id: str, period_start: str, period_end: str) -> dict[str, float]:
    """Aggregate usage events for a billing period."""
    d = await db.get_db()
    cursor = await d.execute(
        """SELECT metric, SUM(units) as total
           FROM billing_usage_events
           WHERE user_id = ? AND created_at >= ? AND created_at < ?
           GROUP BY metric""",
        (user_id, period_start, period_end),
    )
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


# ──────────────────────────────────────────────
#  Invoices
# ──────────────────────────────────────────────

async def generate_invoice(user_id: str, subscription_id: str | None = None) -> dict:
    """Generate a draft invoice for a user (subscription + usage)."""
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
            # Check plan limit
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

    # Create invoice
    invoice = {
        "id": inv_id,
        "user_id": user_id,
        "subscription_id": sub["id"] if sub else None,
        "number": inv_number,
        "status": "draft",
        "payment_status": "pending",
        "currency": CURRENCY,
        "subtotal_cents": total_cents,
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

    logger.info("Generated invoice %s for user %s (total: $%.2f)",
                inv_id, user_id, total_cents / 100)
    return {**invoice, "items": items}


async def finalize_invoice(invoice_id: str) -> dict:
    """Finalize a draft invoice — makes it immutable, triggers payment."""
    inv = await db.fetch_one("billing_invoices", id=invoice_id)
    if not inv:
        raise NotFoundError("Invoice", invoice_id)
    if inv["status"] != "draft":
        raise ValidationError(f"Invoice is already {inv['status']}")

    now = datetime.now(timezone.utc).isoformat()

    # Try wallet deduction
    user = await db.fetch_one("users", id=inv["user_id"])
    credits_used = 0
    remaining = inv["total_cents"]

    if user and user["balance"] > 0:
        balance_cents = int(user["balance"] * 100)
        credits_used = min(balance_cents, remaining)
        remaining -= credits_used
        new_balance = (balance_cents - credits_used) / 100
        await db.update("users", user["id"], {"balance": new_balance})

        if credits_used > 0:
            await db.insert("transactions", {
                "id": f"txn_{token_gen.token_hex(12)}",
                "user_id": inv["user_id"],
                "type": "charge",
                "amount": -(credits_used / 100),
                "description": f"Invoice {inv['number']}",
                "reference": invoice_id,
            })

    payment_status = "succeeded" if remaining == 0 else "pending"
    await db.update("billing_invoices", invoice_id, {
        "status": "finalized",
        "credits_applied_cents": credits_used,
        "total_cents": remaining,
        "payment_status": payment_status,
        "finalized_at": now,
        "paid_at": now if payment_status == "succeeded" else None,
    })

    logger.info("Finalized invoice %s (credits=%d, remaining=%d, status=%s)",
                invoice_id, credits_used, remaining, payment_status)

    inv["status"] = "finalized"
    inv["credits_applied_cents"] = credits_used
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
        # Unset other defaults
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
#  Stripe Integration helpers
# ──────────────────────────────────────────────

async def create_checkout_session(
    user_id: str, plan_code: str, success_url: str, cancel_url: str,
) -> dict:
    """Create a Stripe checkout session for a plan subscription.
    Returns the session data to be used by the frontend.
    Requires STRIPE_SECRET_KEY env var.
    """
    import os
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise ValidationError("Stripe is not configured. Set STRIPE_SECRET_KEY.")

    plan = await get_plan(plan_code)
    if plan["amount_cents"] == 0:
        # Free plan — just subscribe directly
        sub = await create_subscription(user_id, plan_code)
        return {"subscription": sub, "free": True}

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(stripe_key, ""),
            data={
                "mode": "subscription",
                "payment_method_types[]": ["card"],
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
            },
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
) -> dict:
    """Create a Stripe checkout session for wallet top-up."""
    import os
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise ValidationError("Stripe is not configured. Set STRIPE_SECRET_KEY.")

    user = await db.fetch_one("users", id=user_id)
    if not user:
        raise NotFoundError("User", user_id)

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(stripe_key, ""),
            data={
                "mode": "payment",
                "payment_method_types[]": ["card"],
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
            },
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
            # Wallet top-up completed
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
                logger.info("Stripe top-up completed: user=%s amount=$%.2f", user_id, amount)
            return {"handled": True, "type": "topup"}

        else:
            # Plan subscription
            plan_code = metadata.get("plan_code")
            if user_id and plan_code:
                sub = await create_subscription(user_id, plan_code)

                # Register payment method from Stripe
                stripe_customer = data.get("customer")
                if stripe_customer:
                    await add_payment_method(
                        user_id, "card", "stripe",
                        stripe_customer, "Stripe Card",
                        is_default=True,
                    )
                logger.info("Stripe subscription activated: user=%s plan=%s", user_id, plan_code)
                return {"handled": True, "type": "subscription", "subscription_id": sub["id"]}

    elif event_type == "invoice.payment_succeeded":
        stripe_sub = data.get("subscription")
        if stripe_sub:
            # Mark corresponding invoice as paid
            logger.info("Stripe payment succeeded for subscription %s", stripe_sub)
            return {"handled": True, "type": "payment_succeeded"}

    elif event_type == "invoice.payment_failed":
        stripe_sub = data.get("subscription")
        if stripe_sub:
            logger.warning("Stripe payment failed for subscription %s", stripe_sub)
            return {"handled": True, "type": "payment_failed"}

    elif event_type == "customer.subscription.deleted":
        # Customer cancelled in Stripe portal
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

    # Current period usage
    usage = {}
    if sub:
        usage = await get_usage_summary(
            user_id, sub["current_period_start"],
            datetime.now(timezone.utc).isoformat(),
        )

    return {
        "balance": user["balance"] if user else 0,
        "currency": CURRENCY,
        "plan": plan,
        "subscription": sub,
        "invoices": invoices[:10],  # last 10
        "payment_methods": payment_methods,
        "transactions": transactions[:20],  # last 20
        "usage": usage,
    }
