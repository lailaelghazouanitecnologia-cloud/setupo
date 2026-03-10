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

from nso.shared.deps import require_user, require_admin, AuthContext
from nso.shared import db, billing
from nso.shared.errors import NsoError

logger = logging.getLogger("nso.billing")
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

@router.get("/plans", summary="List billing plans")
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

@router.get("/subscription", summary="Get subscription")
async def get_subscription(auth: AuthContext = Depends(require_user)):
    """Get current user's active subscription."""
    sub = await billing.get_subscription(auth.user_id)
    if not sub:
        return {"subscription": None, "plan": None}
    plan = await db.fetch_one("billing_plans", id=sub["plan_id"])
    return {"subscription": sub, "plan": plan}


@router.post("/subscribe", summary="Subscribe to plan")
async def subscribe(req: SubscribeRequest, auth: AuthContext = Depends(require_user)):
    """Subscribe to a plan (free plans only — paid plans use /checkout)."""
    try:
        plan = await billing.get_plan(req.plan_code)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    if plan["amount_cents"] > 0 and not req.trial:
        raise HTTPException(400, "Paid plans require checkout. Use POST /billing/checkout instead.")

    try:
        sub = await billing.create_subscription(auth.user_id, req.plan_code, trial=req.trial)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


@router.post("/cancel", summary="Cancel subscription")
async def cancel_subscription(auth: AuthContext = Depends(require_user)):
    """Cancel the current subscription."""
    try:
        sub = await billing.cancel_subscription(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


@router.post("/pause", summary="Pause subscription")
async def pause_subscription(auth: AuthContext = Depends(require_user)):
    """Pause the current subscription."""
    try:
        sub = await billing.pause_subscription(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


@router.post("/resume", summary="Resume subscription")
async def resume_subscription(auth: AuthContext = Depends(require_user)):
    """Resume a paused subscription."""
    try:
        sub = await billing.resume_subscription(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "subscription": sub}


# ──────────────────────────────────────────────
#  Coupons
# ──────────────────────────────────────────────

@router.get("/coupons", summary="List coupons")
async def list_coupons(auth: AuthContext = Depends(require_admin)):
    """List all coupons (admin only)."""
    coupons = await billing.list_coupons(active_only=False)
    return {"coupons": coupons, "count": len(coupons)}


@router.post("/coupons", summary="Create coupon")
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
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "coupon": coupon}


@router.post("/coupons/{code}/deactivate", summary="Deactivate coupon")
async def deactivate_coupon(code: str, auth: AuthContext = Depends(require_admin)):
    """Deactivate a coupon (admin only)."""
    try:
        coupon = await billing.deactivate_coupon(code)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "coupon": coupon}


@router.post("/coupons/apply", summary="Apply coupon code")
async def apply_coupon(req: ApplyCouponRequest, auth: AuthContext = Depends(require_user)):
    """Apply a coupon code to the current user."""
    sub = await billing.get_subscription(auth.user_id)
    try:
        applied = await billing.apply_coupon(
            auth.user_id, req.coupon_code,
            subscription_id=sub["id"] if sub else None,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "applied_coupon": applied}


@router.delete("/coupons/applied/{applied_id}", summary="Remove applied coupon")
async def remove_applied_coupon(applied_id: str, auth: AuthContext = Depends(require_user)):
    """Remove an applied coupon."""
    try:
        await billing.remove_applied_coupon(auth.user_id, applied_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.get("/coupons/applied", summary="List applied coupons")
async def list_applied_coupons(auth: AuthContext = Depends(require_user)):
    """List user's active applied coupons."""
    applied = await billing.list_applied_coupons(auth.user_id)
    return {"applied_coupons": applied, "count": len(applied)}


# ──────────────────────────────────────────────
#  Credit Notes
# ──────────────────────────────────────────────

@router.get("/credit-notes", summary="List credit notes")
async def list_credit_notes(auth: AuthContext = Depends(require_user)):
    """List user's credit notes."""
    notes = await billing.list_credit_notes(auth.user_id)
    return {"credit_notes": notes, "count": len(notes)}


@router.post("/credit-notes", summary="Create credit note")
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
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "credit_note": cn}


@router.get("/credit-notes/{cn_id}", summary="Get credit note")
async def get_credit_note(cn_id: str, auth: AuthContext = Depends(require_user)):
    """Get a credit note."""
    try:
        cn = await billing.get_credit_note(cn_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    if cn["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    return {"credit_note": cn}


@router.post("/credit-notes/{cn_id}/void", summary="Void credit note")
async def void_credit_note(cn_id: str, auth: AuthContext = Depends(require_admin)):
    """Void a credit note (admin only)."""
    try:
        cn = await billing.void_credit_note(cn_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "credit_note": cn}


# ──────────────────────────────────────────────
#  Billable Metrics
# ──────────────────────────────────────────────

@router.get("/metrics", summary="List billable metrics")
async def list_billable_metrics(auth: AuthContext = Depends(require_admin)):
    """List all billable metrics (admin only)."""
    metrics = await billing.list_billable_metrics()
    return {"metrics": metrics, "count": len(metrics)}


@router.post("/metrics", summary="Create billable metric")
async def create_billable_metric(req: BillableMetricRequest, auth: AuthContext = Depends(require_admin)):
    """Create a billable metric (admin only)."""
    try:
        m = await billing.create_billable_metric(
            code=req.code, name=req.name, aggregation_type=req.aggregation_type,
            description=req.description, field_name=req.field_name,
            recurring=req.recurring, filters=req.filters,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "metric": m}


@router.patch("/metrics/{code}", summary="Update billable metric")
async def update_billable_metric(code: str, updates: dict, auth: AuthContext = Depends(require_admin)):
    """Update a billable metric (admin only)."""
    try:
        m = await billing.update_billable_metric(code, updates)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "metric": m}


@router.delete("/metrics/{code}", summary="Delete billable metric")
async def delete_billable_metric(code: str, auth: AuthContext = Depends(require_admin)):
    """Delete a billable metric (admin only)."""
    try:
        await billing.delete_billable_metric(code)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ──────────────────────────────────────────────
#  Usage Events
# ──────────────────────────────────────────────

@router.post("/usage", summary="Record usage event")
async def record_usage(req: UsageEventRequest, auth: AuthContext = Depends(require_user)):
    """Record a usage event for the current user."""
    event_id = await billing.record_usage(
        auth.user_id, req.metric, req.units,
        properties=req.properties, transaction_id=req.transaction_id,
    )
    return {"ok": True, "event_id": event_id}


@router.get("/usage/summary", summary="Get usage summary")
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

@router.get("/taxes", summary="List tax rates")
async def list_tax_rates(auth: AuthContext = Depends(require_admin)):
    """List tax rates (admin only)."""
    taxes = await billing.list_tax_rates(active_only=False)
    return {"taxes": taxes, "count": len(taxes)}


@router.post("/taxes", summary="Create tax rate")
async def create_tax_rate(req: TaxRateRequest, auth: AuthContext = Depends(require_admin)):
    """Create a tax rate (admin only)."""
    try:
        tax = await billing.create_tax_rate(
            name=req.name, code=req.code, rate=req.rate,
            description=req.description, applied_to=req.applied_to, region=req.region,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "tax": tax}


@router.patch("/taxes/{code}", summary="Update tax rate")
async def update_tax_rate(code: str, updates: dict, auth: AuthContext = Depends(require_admin)):
    """Update a tax rate (admin only)."""
    try:
        tax = await billing.update_tax_rate(code, updates)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "tax": tax}


# ──────────────────────────────────────────────
#  Wallets
# ──────────────────────────────────────────────

@router.get("/wallets", summary="List wallets")
async def list_wallets(auth: AuthContext = Depends(require_user)):
    """List user's wallets."""
    wallets = await billing.list_wallets(auth.user_id)
    return {"wallets": wallets, "count": len(wallets)}


@router.post("/wallets", summary="Create wallet")
async def create_wallet(req: WalletCreateRequest, auth: AuthContext = Depends(require_user)):
    """Create a prepaid wallet."""
    try:
        wallet = await billing.create_wallet(
            auth.user_id, name=req.name,
            paid_credits=req.paid_credits, granted_credits=req.granted_credits,
            rate_amount=req.rate_amount, expiration_at=req.expiration_at,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "wallet": wallet}


@router.get("/wallets/{wallet_id}", summary="Get wallet")
async def get_wallet(wallet_id: str, auth: AuthContext = Depends(require_user)):
    """Get a wallet."""
    try:
        wallet = await billing.get_wallet(wallet_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    if wallet["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    return {"wallet": wallet}


@router.post("/wallets/{wallet_id}/topup", summary="Top up wallet")
async def top_up_wallet(wallet_id: str, req: WalletTopUpRequest, auth: AuthContext = Depends(require_user)):
    """Top up a wallet with credits."""
    try:
        wallet = await billing.get_wallet(wallet_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    if wallet["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    try:
        wallet = await billing.top_up_wallet(wallet_id, req.paid_credits, req.granted_credits)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "wallet": wallet}


@router.get("/wallets/{wallet_id}/transactions", summary="List wallet transactions")
async def wallet_transactions(wallet_id: str, auth: AuthContext = Depends(require_user)):
    """List transactions for a wallet."""
    try:
        wallet = await billing.get_wallet(wallet_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    if wallet["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    txns = await billing.get_wallet_transactions(wallet_id)
    return {"transactions": txns, "count": len(txns)}


# ──────────────────────────────────────────────
#  Stripe Checkout
# ──────────────────────────────────────────────

@router.post("/checkout", summary="Create Stripe checkout")
async def create_checkout(req: CheckoutRequest, auth: AuthContext = Depends(require_user)):
    """Create a Stripe checkout session for a paid plan."""
    success_url = req.success_url or "https://nso.dev/dashboard?billing=success"
    cancel_url = req.cancel_url or "https://nso.dev/dashboard?billing=cancelled"
    try:
        result = await billing.create_checkout_session(
            auth.user_id, req.plan_code, success_url, cancel_url,
            payment_methods=req.payment_methods,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/topup/checkout", summary="Create top-up checkout")
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
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


@router.post("/stripe/webhook", summary="Handle Stripe webhook")
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

@router.get("/invoices", summary="List invoices")
async def list_invoices(auth: AuthContext = Depends(require_user)):
    """List user's invoices."""
    invoices = await billing.list_invoices(auth.user_id)
    return {"invoices": invoices, "count": len(invoices)}


@router.get("/invoices/{invoice_id}", summary="Get invoice")
async def get_invoice(invoice_id: str, auth: AuthContext = Depends(require_user)):
    """Get a specific invoice with line items."""
    try:
        inv = await billing.get_invoice(invoice_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    if inv["user_id"] != auth.user_id and not auth.is_admin:
        raise HTTPException(403, "Access denied")
    return {"invoice": inv}


@router.post("/invoices/generate", summary="Generate draft invoice")
async def generate_invoice(auth: AuthContext = Depends(require_user)):
    """Generate a draft invoice for the current billing period."""
    try:
        inv = await billing.generate_invoice(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invoice": inv}


@router.post("/invoices/{invoice_id}/finalize", summary="Finalize invoice")
async def finalize_invoice(invoice_id: str, auth: AuthContext = Depends(require_admin)):
    """Finalize a draft invoice (admin only)."""
    try:
        inv = await billing.finalize_invoice(invoice_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invoice": inv}


@router.post("/invoices/{invoice_id}/void", summary="Void invoice")
async def void_invoice(invoice_id: str, auth: AuthContext = Depends(require_admin)):
    """Void an invoice (admin only)."""
    try:
        inv = await billing.void_invoice(invoice_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invoice": inv}


# ──────────────────────────────────────────────
#  Payment Methods
# ──────────────────────────────────────────────

@router.get("/payment-methods", summary="List payment methods")
async def list_payment_methods(auth: AuthContext = Depends(require_user)):
    """List user's payment methods."""
    methods = await billing.list_payment_methods(auth.user_id)
    return {"payment_methods": methods}


@router.delete("/payment-methods/{pm_id}", summary="Remove payment method")
async def remove_payment_method(pm_id: str, auth: AuthContext = Depends(require_user)):
    """Remove a payment method."""
    try:
        await billing.remove_payment_method(pm_id, auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.post("/payment-methods/{pm_id}/default", summary="Set default payment method")
async def set_default_pm(pm_id: str, auth: AuthContext = Depends(require_user)):
    """Set a payment method as default."""
    try:
        pm = await billing.set_default_payment_method(pm_id, auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "payment_method": pm}


# ──────────────────────────────────────────────
#  Wallet (legacy balance + transactions)
# ──────────────────────────────────────────────

@router.get("/balance", summary="Get balance")
async def get_balance(auth: AuthContext = Depends(require_user)):
    """Get current wallet balance."""
    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"balance_cents": user.get("balance_cents", 0), "currency": "USD"}


@router.get("/transactions", summary="List transactions")
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


@router.post("/topup", summary="Top up balance")
async def top_up(req: TopUpRequest, auth: AuthContext = Depends(require_admin)):
    """Top up wallet balance (admin only — for real payments use /topup/checkout)."""
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if req.amount > MAX_TOPUP_AMOUNT:
        raise HTTPException(400, f"Maximum top-up is ${MAX_TOPUP_AMOUNT:.0f}")

    user = await db.fetch_one("users", id=req.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    amount_cents = int(req.amount * 100)
    new_balance_cents = user.get("balance_cents", 0) + amount_cents
    txn_id = f"txn_{stdlib_secrets.token_hex(12)}"

    await db.insert("transactions", {
        "id": txn_id,
        "user_id": req.user_id,
        "type": "topup",
        "amount": req.amount,
        "description": f"Balance top-up: ${req.amount:.2f}",
        "reference": req.reference,
    })
    await db.update("users", req.user_id, {"balance_cents": new_balance_cents})

    logger.info("Top-up: %s +$%.2f (balance_cents: %d)", req.user_id, req.amount, new_balance_cents)
    return {"ok": True, "balance_cents": new_balance_cents, "transaction_id": txn_id}


@router.post("/charge", summary="Charge user")
async def charge_user(req: ChargeRequest, auth: AuthContext = Depends(require_admin)):
    """Charge a user (admin only)."""
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    user = await db.fetch_one("users", id=req.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    amount_cents = int(req.amount * 100)
    current_cents = user.get("balance_cents", 0)
    if current_cents < amount_cents:
        raise HTTPException(400, f"Insufficient balance: ${current_cents / 100:.2f}")

    new_balance_cents = current_cents - amount_cents
    txn_id = f"txn_{stdlib_secrets.token_hex(12)}"

    await db.insert("transactions", {
        "id": txn_id,
        "user_id": req.user_id,
        "type": "charge",
        "amount": -req.amount,
        "description": req.description or f"Service charge: ${req.amount:.2f}",
        "reference": req.reference,
    })
    await db.update("users", req.user_id, {"balance_cents": new_balance_cents})

    logger.info("Charge: %s -$%.2f (balance_cents: %d)", req.user_id, req.amount, new_balance_cents)
    return {"ok": True, "balance_cents": new_balance_cents, "transaction_id": txn_id}


# ──────────────────────────────────────────────
#  Billing Events (audit trail)
# ──────────────────────────────────────────────

@router.get("/events", summary="List billing events")
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


@router.get("/events/user", summary="List user billing events")
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

@router.get("/overview", summary="Get billing overview")
async def billing_overview(auth: AuthContext = Depends(require_user)):
    """Complete billing overview for the dashboard."""
    try:
        overview = await billing.get_billing_overview(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return overview


# ──────────────────────────────────────────────
#  Admin: list users with balances
# ──────────────────────────────────────────────

@router.get("/users", summary="List users with billing")
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
                "balance_cents": u.get("balance_cents", 0),
                "verified": u["verified"],
                "created_at": u["created_at"],
            }
            for u in users
        ],
        "count": len(users),
    }
