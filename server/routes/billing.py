"""
nso-billing API routes.

Plans, subscriptions, invoices, payment methods, Stripe checkout + webhooks, wallet top-up.
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
    amount: float
    reference: str = ""


class ChargeRequest(BaseModel):
    user_id: str
    amount: float
    description: str = ""
    reference: str = ""


class SubscribeRequest(BaseModel):
    plan_code: str


class CheckoutRequest(BaseModel):
    plan_code: str
    success_url: str = ""
    cancel_url: str = ""


class TopUpCheckoutRequest(BaseModel):
    amount_cents: int
    success_url: str = ""
    cancel_url: str = ""


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

    if plan["amount_cents"] > 0:
        raise HTTPException(400, "Paid plans require checkout. Use POST /billing/checkout instead.")

    try:
        sub = await billing.create_subscription(auth.user_id, req.plan_code)
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

    if webhook_secret and sig:
        # Verify webhook signature
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
#  Wallet (balance + transactions)
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
async def top_up(req: TopUpRequest, auth: AuthContext = Depends(require_user)):
    """Top up wallet balance (simulated — for real payments use /topup/checkout)."""
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if req.amount > MAX_TOPUP_AMOUNT:
        raise HTTPException(400, f"Maximum top-up is ${MAX_TOPUP_AMOUNT:.0f}")

    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    new_balance = user["balance"] + req.amount
    txn_id = f"txn_{stdlib_secrets.token_hex(12)}"

    await db.insert("transactions", {
        "id": txn_id,
        "user_id": auth.user_id,
        "type": "topup",
        "amount": req.amount,
        "description": f"Balance top-up: ${req.amount:.2f}",
        "reference": req.reference,
    })
    await db.update("users", auth.user_id, {"balance": new_balance})

    logger.info("Top-up: %s +$%.2f (balance: $%.2f)", auth.user_id, req.amount, new_balance)
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
