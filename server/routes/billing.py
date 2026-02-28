"""
nso-billing API routes.

Plans, subscriptions, coupons, credit notes, billable metrics, tax rates,
wallets, invoices, payment methods, Stripe checkout + webhooks, billing events.
"""
import hashlib
import hmac
import logging
import os
import secrets as stdlib_secrets

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from server.deps import require_user, require_admin, AuthContext
from core import db, billing
from core.errors import SetupoError

logger = logging.getLogger("setupo.billing")
router = APIRouter()

MAX_TOPUP_AMOUNT = 1000.0


# ──────────────────────────────────────────────
#  Request / Response models
# ──────────────────────────────────────────────

class TopUpRequest(BaseModel):
    user_id: str
    amount: float
    reference: str = ""


class ChargeRequest(BaseModel):
    user_id: str
    amount: float
    description: str = ""
    reference: str = ""


class SubscribeRequest(BaseModel):
    plan_code: str
    trial: bool = False


class CheckoutRequest(BaseModel):
    plan_code: str
    success_url: str = ""
    cancel_url: str = ""
    payment_methods: list[str] | None = None


class TopUpCheckoutRequest(BaseModel):
    amount_cents: int
    success_url: str = ""
    cancel_url: str = ""
    payment_methods: list[str] | None = None


class CouponCreateRequest(BaseModel):
    code: str
    name: str
    coupon_type: str = "percentage"
    value: int = 0
    frequency: str = "once"
    frequency_duration: int = 0
    plan_codes: list[str] | None = None
    max_redemptions: int = 0
    expires_at: str | None = None


class ApplyCouponRequest(BaseModel):
    coupon_code: str


class CreditNoteRequest(BaseModel):
    user_id: str = ""
    invoice_id: str | None = None
    total_cents: int = 0
    reason: str = ""
    credit_type: str = "refund"


class BillableMetricRequest(BaseModel):
    code: str
    name: str
    aggregation_type: str = "sum"
    description: str = ""
    field_name: str = ""
    recurring: bool = False
    filters: list | None = None


class UsageEventRequest(BaseModel):
    metric: str
    units: float
    properties: dict | None = None
    transaction_id: str | None = None


class TaxRateRequest(BaseModel):
    name: str
    code: str
    rate: float
    description: str = ""
    applied_to: str = "all"
    region: str = ""


class WalletCreateRequest(BaseModel):
    name: str = "Primary"
    paid_credits: float = 0.0
    granted_credits: float = 0.0
    rate_amount: float = 1.0
    expiration_at: str | None = None


class WalletTopUpRequest(BaseModel):
    paid_credits: float = 0.0
    granted_credits: float = 0.0


# ──────────────────────────────────────────────
#  Plans
# ──────────────────────────────────────────────

@router.get("/plans")
async def list_plans():
    """List available billing plans (public)."""
    plans = await billing.list_plans()
    return {
        "plans": [
            {
                "id": p["id"],
                "code": p["code"],
                "name": p["name"],
                "description": p["description"],
                "interval": p["interval"],
                "amount_cents": p["amount_cents"],
                "currency": p["currency"],
                "features": p.get("features", {}),
            }
            for p in plans
        ],
    }


# ──────────────────────────────────────────────
#  Subscriptions
# ──────────────────────────────────────────────

@router.get("/subscription")
async def get_subscription(auth: AuthContext = Depends(require_user)):
    """Get current user's active subscription."""
    sub = await billing.get_subscription(auth.user_id)
    if not sub:
        return {"subscription": None, "plan": None}
    plan = await db.fetch_one("billing_plans", id=sub["plan_id"])
    return {"subscription": sub, "plan": plan}


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest, auth: AuthContext = Depends(require_user)):
    """Subscribe to a plan (free plans only — paid plans use /checkout)."""
    try:
        plan = await billing.get_plan(req.plan_code)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)

    if plan["amount_cents"] > 0 and not req.trial:
        raise HTTPException(400, "Paid plans require checkout. Use POST /billing/checkout instead.")

    try:
        sub = await billing.create_subscription(auth.user_id, req.plan_code, trial=req.trial)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


@router.post("/cancel")
async def cancel_subscription(auth: AuthContext = Depends(require_user)):
    """Cancel the current subscription."""
    try:
        sub = await billing.cancel_subscription(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


@router.post("/pause")
async def pause_subscription(auth: AuthContext = Depends(require_user)):
    """Pause the current subscription."""
    try:
        sub = await billing.pause_subscription(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


@router.post("/resume")
async def resume_subscription(auth: AuthContext = Depends(require_user)):
    """Resume a paused subscription."""
    try:
        sub = await billing.resume_subscription(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


# ──────────────────────────────────────────────
#  Coupons
# ──────────────────────────────────────────────

@router.get("/coupons")
async def list_coupons(auth: AuthContext = Depends(require_admin)):
    """List all coupons (admin only)."""
    coupons = await billing.list_coupons(active_only=False)
    return {"coupons": coupons, "count": len(coupons)}


@router.post("/coupons")
async def create_coupon(req: CouponCreateRequest, auth: AuthContext = Depends(require_admin)):
    """Create a coupon (admin only)."""
    try:
        coupon = await billing.create_coupon(
            code=req.code, name=req.name, coupon_type=req.coupon_type,
            value=req.value, frequency=req.frequency,
            frequency_duration=req.frequency_duration,
            plan_codes=req.plan_codes, max_redemptions=req.max_redemptions,
            expires_at=req.expires_at,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "coupon": coupon}


@router.post("/coupons/{code}/deactivate")
async def deactivate_coupon(code: str, auth: AuthContext = Depends(require_admin)):
    """Deactivate a coupon (admin only)."""
    try:
        coupon = await billing.deactivate_coupon(code)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "coupon": coupon}


@router.post("/coupons/apply")
async def apply_coupon(req: ApplyCouponRequest, auth: AuthContext = Depends(require_user)):
    """Apply a coupon code to the current user."""
    sub = await billing.get_subscription(auth.user_id)
    try:
        applied = await billing.apply_coupon(
            auth.user_id, req.coupon_code,
            subscription_id=sub["id"] if sub else None,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "applied_coupon": applied}


@router.delete("/coupons/applied/{applied_id}")
async def remove_applied_coupon(applied_id: str, auth: AuthContext = Depends(require_user)):
    """Remove an applied coupon."""
    try:
        await billing.remove_applied_coupon(auth.user_id, applied_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.get("/coupons/applied")
async def list_applied_coupons(auth: AuthContext = Depends(require_user)):
    """List user's active applied coupons."""
    applied = await billing.list_applied_coupons(auth.user_id)
    return {"applied_coupons": applied, "count": len(applied)}


# ──────────────────────────────────────────────
#  Credit Notes
# ──────────────────────────────────────────────

@router.get("/credit-notes")
async def list_credit_notes(auth: AuthContext = Depends(require_user)):
    """List user's credit notes."""
    notes = await billing.list_credit_notes(auth.user_id)
    return {"credit_notes": notes, "count": len(notes)}


@router.post("/credit-notes")
async def create_credit_note(req: CreditNoteRequest, auth: AuthContext = Depends(require_admin)):
    """Create a credit note (admin only)."""
    user_id = req.user_id
    if not user_id:
        raise HTTPException(400, "user_id is required")
    try:
        cn = await billing.create_credit_note(
            user_id=user_id, invoice_id=req.invoice_id,
            total_cents=req.total_cents, reason=req.reason,
            credit_type=req.credit_type,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "credit_note": cn}


@router.get("/credit-notes/{cn_id}")
async def get_credit_note(cn_id: str, auth: AuthContext = Depends(require_user)):
    """Get a credit note."""
    try:
        cn = await billing.get_credit_note(cn_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    if cn["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    return {"credit_note": cn}


@router.post("/credit-notes/{cn_id}/void")
async def void_credit_note(cn_id: str, auth: AuthContext = Depends(require_admin)):
    """Void a credit note (admin only)."""
    try:
        cn = await billing.void_credit_note(cn_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "credit_note": cn}


# ──────────────────────────────────────────────
#  Billable Metrics
# ──────────────────────────────────────────────

@router.get("/metrics")
async def list_billable_metrics(auth: AuthContext = Depends(require_admin)):
    """List all billable metrics (admin only)."""
    metrics = await billing.list_billable_metrics()
    return {"metrics": metrics, "count": len(metrics)}


@router.post("/metrics")
async def create_billable_metric(req: BillableMetricRequest, auth: AuthContext = Depends(require_admin)):
    """Create a billable metric (admin only)."""
    try:
        m = await billing.create_billable_metric(
            code=req.code, name=req.name, aggregation_type=req.aggregation_type,
            description=req.description, field_name=req.field_name,
            recurring=req.recurring, filters=req.filters,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "metric": m}


@router.patch("/metrics/{code}")
async def update_billable_metric(code: str, updates: dict, auth: AuthContext = Depends(require_admin)):
    """Update a billable metric (admin only)."""
    try:
        m = await billing.update_billable_metric(code, updates)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "metric": m}


@router.delete("/metrics/{code}")
async def delete_billable_metric(code: str, auth: AuthContext = Depends(require_admin)):
    """Delete a billable metric (admin only)."""
    try:
        await billing.delete_billable_metric(code)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ──────────────────────────────────────────────
#  Usage Events
# ──────────────────────────────────────────────

@router.post("/usage")
async def record_usage(req: UsageEventRequest, auth: AuthContext = Depends(require_user)):
    """Record a usage event for the current user."""
    event_id = await billing.record_usage(
        auth.user_id, req.metric, req.units,
        properties=req.properties, transaction_id=req.transaction_id,
    )
    return {"ok": True, "event_id": event_id}


@router.get("/usage/summary")
async def get_usage_summary(auth: AuthContext = Depends(require_user)):
    """Get usage summary for the current billing period."""
    sub = await billing.get_subscription(auth.user_id)
    if not sub:
        return {"usage": {}, "period_start": None, "period_end": None}

    from datetime import datetime, timezone
    usage = await billing.get_usage_summary(
        auth.user_id, sub["current_period_start"],
        datetime.now(timezone.utc).isoformat(),
    )
    return {
        "usage": usage,
        "period_start": sub["current_period_start"],
        "period_end": sub["current_period_end"],
    }


# ──────────────────────────────────────────────
#  Tax Rates
# ──────────────────────────────────────────────

@router.get("/taxes")
async def list_tax_rates(auth: AuthContext = Depends(require_admin)):
    """List tax rates (admin only)."""
    taxes = await billing.list_tax_rates(active_only=False)
    return {"taxes": taxes, "count": len(taxes)}


@router.post("/taxes")
async def create_tax_rate(req: TaxRateRequest, auth: AuthContext = Depends(require_admin)):
    """Create a tax rate (admin only)."""
    try:
        tax = await billing.create_tax_rate(
            name=req.name, code=req.code, rate=req.rate,
            description=req.description, applied_to=req.applied_to, region=req.region,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "tax": tax}


@router.patch("/taxes/{code}")
async def update_tax_rate(code: str, updates: dict, auth: AuthContext = Depends(require_admin)):
    """Update a tax rate (admin only)."""
    try:
        tax = await billing.update_tax_rate(code, updates)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "tax": tax}


# ──────────────────────────────────────────────
#  Wallets
# ──────────────────────────────────────────────

@router.get("/wallets")
async def list_wallets(auth: AuthContext = Depends(require_user)):
    """List user's wallets."""
    wallets = await billing.list_wallets(auth.user_id)
    return {"wallets": wallets, "count": len(wallets)}


@router.post("/wallets")
async def create_wallet(req: WalletCreateRequest, auth: AuthContext = Depends(require_user)):
    """Create a prepaid wallet."""
    try:
        wallet = await billing.create_wallet(
            auth.user_id, name=req.name,
            paid_credits=req.paid_credits, granted_credits=req.granted_credits,
            rate_amount=req.rate_amount, expiration_at=req.expiration_at,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "wallet": wallet}


@router.get("/wallets/{wallet_id}")
async def get_wallet(wallet_id: str, auth: AuthContext = Depends(require_user)):
    """Get a wallet."""
    try:
        wallet = await billing.get_wallet(wallet_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    if wallet["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    return {"wallet": wallet}


@router.post("/wallets/{wallet_id}/topup")
async def top_up_wallet(wallet_id: str, req: WalletTopUpRequest, auth: AuthContext = Depends(require_user)):
    """Top up a wallet with credits."""
    try:
        wallet = await billing.get_wallet(wallet_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    if wallet["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    try:
        wallet = await billing.top_up_wallet(wallet_id, req.paid_credits, req.granted_credits)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "wallet": wallet}


@router.get("/wallets/{wallet_id}/transactions")
async def wallet_transactions(wallet_id: str, auth: AuthContext = Depends(require_user)):
    """List transactions for a wallet."""
    try:
        wallet = await billing.get_wallet(wallet_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    if wallet["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    txns = await billing.get_wallet_transactions(wallet_id)
    return {"transactions": txns, "count": len(txns)}


# ──────────────────────────────────────────────
#  Stripe Checkout
# ──────────────────────────────────────────────

@router.post("/checkout")
async def create_checkout(req: CheckoutRequest, auth: AuthContext = Depends(require_user)):
    """Create a Stripe checkout session for a paid plan."""
    success_url = req.success_url or "https://nso.dev/dashboard?billing=success"
    cancel_url = req.cancel_url or "https://nso.dev/dashboard?billing=cancelled"
    try:
        result = await billing.create_checkout_session(
            auth.user_id, req.plan_code, success_url, cancel_url,
            payment_methods=req.payment_methods,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/topup/checkout")
async def create_topup_checkout(req: TopUpCheckoutRequest, auth: AuthContext = Depends(require_user)):
    """Create a Stripe checkout session for wallet top-up."""
    if req.amount_cents < 500:
        raise HTTPException(400, "Minimum top-up is $5.00")
    if req.amount_cents > 100000:
        raise HTTPException(400, "Maximum top-up is $1,000.00")

    success_url = req.success_url or "https://nso.dev/dashboard?topup=success"
    cancel_url = req.cancel_url or "https://nso.dev/dashboard?topup=cancelled"
    try:
        result = await billing.create_topup_checkout(
            auth.user_id, req.amount_cents, success_url, cancel_url,
            payment_methods=req.payment_methods,
        )
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook handler. Verifies signature, processes events."""
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(500, "Webhook not configured")
    if not sig:
        raise HTTPException(400, "Missing stripe-signature header")

    try:
        _verify_stripe_signature(body, sig, webhook_secret)
    except Exception as e:
        logger.warning("Stripe webhook signature verification failed: %s", e)
        raise HTTPException(400, "Invalid signature")

    import json
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    result = await billing.handle_stripe_webhook(payload)
    return result


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str):
    """Verify Stripe webhook signature (v1 scheme)."""
    parts = {kv.split("=")[0]: kv.split("=")[1] for kv in sig_header.split(",") if "=" in kv}
    timestamp = parts.get("t", "")
    v1_sig = parts.get("v1", "")
    if not timestamp or not v1_sig:
        raise ValueError("Missing timestamp or signature")

    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1_sig):
        raise ValueError("Signature mismatch")


# ──────────────────────────────────────────────
#  Invoices
# ──────────────────────────────────────────────

@router.get("/invoices")
async def list_invoices(auth: AuthContext = Depends(require_user)):
    """List user's invoices."""
    invoices = await billing.list_invoices(auth.user_id)
    return {"invoices": invoices, "count": len(invoices)}


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, auth: AuthContext = Depends(require_user)):
    """Get a specific invoice with line items."""
    try:
        inv = await billing.get_invoice(invoice_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    if inv["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    return {"invoice": inv}


@router.post("/invoices/generate")
async def generate_invoice(auth: AuthContext = Depends(require_user)):
    """Generate a draft invoice for the current billing period."""
    try:
        inv = await billing.generate_invoice(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invoice": inv}


@router.post("/invoices/{invoice_id}/finalize")
async def finalize_invoice(invoice_id: str, auth: AuthContext = Depends(require_admin)):
    """Finalize a draft invoice (admin only)."""
    try:
        inv = await billing.finalize_invoice(invoice_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invoice": inv}


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: str, auth: AuthContext = Depends(require_admin)):
    """Void an invoice (admin only)."""
    try:
        inv = await billing.void_invoice(invoice_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invoice": inv}


# ──────────────────────────────────────────────
#  Payment Methods
# ──────────────────────────────────────────────

@router.get("/payment-methods")
async def list_payment_methods(auth: AuthContext = Depends(require_user)):
    """List user's payment methods."""
    methods = await billing.list_payment_methods(auth.user_id)
    return {"payment_methods": methods}


@router.delete("/payment-methods/{pm_id}")
async def remove_payment_method(pm_id: str, auth: AuthContext = Depends(require_user)):
    """Remove a payment method."""
    try:
        await billing.remove_payment_method(pm_id, auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.post("/payment-methods/{pm_id}/default")
async def set_default_pm(pm_id: str, auth: AuthContext = Depends(require_user)):
    """Set a payment method as default."""
    try:
        pm = await billing.set_default_payment_method(pm_id, auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "payment_method": pm}


# ──────────────────────────────────────────────
#  Wallet (legacy balance + transactions)
# ──────────────────────────────────────────────

@router.get("/balance")
async def get_balance(auth: AuthContext = Depends(require_user)):
    """Get current wallet balance."""
    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"balance": user["balance"], "currency": "USD"}


@router.get("/transactions")
async def list_transactions(auth: AuthContext = Depends(require_user)):
    """List wallet transactions."""
    txns = await db.fetch_all("transactions", user_id=auth.user_id)
    return {
        "transactions": [
            {
                "id": t["id"],
                "type": t["type"],
                "amount": t["amount"],
                "description": t["description"],
                "reference": t["reference"],
                "created_at": t["created_at"],
            }
            for t in txns
        ],
        "count": len(txns),
    }


@router.post("/topup")
async def top_up(req: TopUpRequest, auth: AuthContext = Depends(require_admin)):
    """Top up wallet balance (admin only — for real payments use /topup/checkout)."""
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if req.amount > MAX_TOPUP_AMOUNT:
        raise HTTPException(400, f"Maximum top-up is ${MAX_TOPUP_AMOUNT:.0f}")

    user = await db.fetch_one("users", id=req.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    new_balance = user["balance"] + req.amount
    txn_id = f"txn_{stdlib_secrets.token_hex(12)}"

    await db.insert("transactions", {
        "id": txn_id,
        "user_id": req.user_id,
        "type": "topup",
        "amount": req.amount,
        "description": f"Balance top-up: ${req.amount:.2f}",
        "reference": req.reference,
    })
    await db.update("users", req.user_id, {"balance": new_balance})

    logger.info("Top-up: %s +$%.2f (balance: $%.2f)", req.user_id, req.amount, new_balance)
    return {"ok": True, "balance": new_balance, "transaction_id": txn_id}


@router.post("/charge")
async def charge_user(req: ChargeRequest, auth: AuthContext = Depends(require_admin)):
    """Charge a user (admin only)."""
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    user = await db.fetch_one("users", id=req.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user["balance"] < req.amount:
        raise HTTPException(400, f"Insufficient balance: ${user['balance']:.2f}")

    new_balance = user["balance"] - req.amount
    txn_id = f"txn_{stdlib_secrets.token_hex(12)}"

    await db.insert("transactions", {
        "id": txn_id,
        "user_id": req.user_id,
        "type": "charge",
        "amount": -req.amount,
        "description": req.description or f"Service charge: ${req.amount:.2f}",
        "reference": req.reference,
    })
    await db.update("users", req.user_id, {"balance": new_balance})

    logger.info("Charge: %s -$%.2f (balance: $%.2f)", req.user_id, req.amount, new_balance)
    return {"ok": True, "balance": new_balance, "transaction_id": txn_id}


# ──────────────────────────────────────────────
#  Billing Events (audit trail)
# ──────────────────────────────────────────────

@router.get("/events")
async def list_billing_events(
    event_type: str = "", limit: int = 50,
    auth: AuthContext = Depends(require_admin),
):
    """List billing events (admin: all, user: own)."""
    events = await billing.list_billing_events(
        user_id=None if auth.is_admin else auth.user_id,
        event_type=event_type or None,
        limit=min(limit, 200),
    )
    return {"events": events, "count": len(events)}


@router.get("/events/user")
async def list_user_billing_events(
    event_type: str = "", limit: int = 50,
    auth: AuthContext = Depends(require_user),
):
    """List user's own billing events."""
    events = await billing.list_billing_events(
        user_id=auth.user_id,
        event_type=event_type or None,
        limit=min(limit, 100),
    )
    return {"events": events, "count": len(events)}


# ──────────────────────────────────────────────
#  Billing overview
# ──────────────────────────────────────────────

@router.get("/overview")
async def billing_overview(auth: AuthContext = Depends(require_user)):
    """Complete billing overview for the dashboard."""
    try:
        overview = await billing.get_billing_overview(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    return overview


# ──────────────────────────────────────────────
#  Admin: list users with balances
# ──────────────────────────────────────────────

@router.get("/users")
async def list_users(auth: AuthContext = Depends(require_admin)):
    """List all users with billing info (admin only)."""
    users = await db.fetch_all("users")
    return {
        "users": [
            {
                "id": u["id"],
                "email": u["email"],
                "name": u["name"],
                "role": u["role"],
                "balance": u["balance"],
                "verified": u["verified"],
                "created_at": u["created_at"],
            }
            for u in users
        ],
        "count": len(users),
    }
