"""Billing Routes — Balance, transactions, top-up, charges."""
import logging
import secrets as stdlib_secrets

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.deps import require_user, require_admin, AuthContext
from core import db

logger = logging.getLogger("setupo.billing")
router = APIRouter()


class TopUpRequest(BaseModel):
    amount: float
    reference: str = ""


class ChargeRequest(BaseModel):
    user_id: str
    amount: float
    description: str = ""
    reference: str = ""


class TransactionOut(BaseModel):
    id: str
    type: str
    amount: float
    description: str
    reference: str
    created_at: str


class BalanceOut(BaseModel):
    balance: float
    currency: str = "USD"


# ── User endpoints ─────────────────────────────────────────

@router.get("/balance", response_model=BalanceOut)
async def get_balance(auth: AuthContext = Depends(require_user)):
    """Get current user balance."""
    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return BalanceOut(balance=user["balance"])


@router.get("/transactions")
async def list_transactions(auth: AuthContext = Depends(require_user)):
    """List user transactions."""
    txns = await db.fetch_all("transactions", user_id=auth.user_id)
    return {
        "transactions": [
            TransactionOut(
                id=t["id"],
                type=t["type"],
                amount=t["amount"],
                description=t["description"],
                reference=t["reference"],
                created_at=t["created_at"],
            )
            for t in txns
        ],
        "count": len(txns),
    }


@router.post("/topup")
async def top_up(req: TopUpRequest, auth: AuthContext = Depends(require_user)):
    """Simulate adding balance (in production, integrate payment gateway)."""
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if req.amount > 1000:
        raise HTTPException(400, "Maximum top-up is $1000")

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


# ── Admin endpoints ────────────────────────────────────────

@router.post("/charge")
async def charge_user(req: ChargeRequest, auth: AuthContext = Depends(require_admin)):
    """Admin: charge a user's balance."""
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


@router.get("/users")
async def list_users(auth: AuthContext = Depends(require_admin)):
    """Admin: list all users with balances."""
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
