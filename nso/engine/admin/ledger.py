"""
NSO Blockchain — Immutable transaction ledger for financial traceability.

Every monetary operation (wallet top-up, invoice payment, refund, credit note,
subscription charge, coupon discount) is recorded as a block in a hash-linked
chain. Blocks cannot be tampered with: each block includes the SHA-256 hash
of the previous block, ensuring integrity.

Fraud detection: if any row is modified, the chain breaks and the audit
system flags the exact point of corruption.
"""
import asyncio
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timezone

from nso.shared import db
from nso.shared.errors import NsoError, ValidationError

logger = logging.getLogger("nso.blockchain")

_USER_ID_RE = re.compile(r"^user_[a-f0-9]{24}$")

# Per-user write locks to prevent concurrent chain corruption.
_chain_locks: dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


async def _get_lock(user_id: str) -> asyncio.Lock:
    async with _locks_lock:
        if user_id not in _chain_locks:
            _chain_locks[user_id] = asyncio.Lock()
        return _chain_locks[user_id]


def _validate_user_id(user_id: str):
    if not _USER_ID_RE.match(user_id):
        raise ValidationError("Invalid user_id format")


# ── Block types with expected amount sign ──
# positive = money in, negative = money out, zero = neutral
BLOCK_SIGN: dict[str, int] = {
    "wallet_topup":         1,
    "wallet_debit":        -1,
    "wallet_grant":         1,
    "invoice_charge":      -1,
    "invoice_refund":       1,
    "invoice_void":         0,
    "subscription_charge": -1,
    "subscription_credit":  1,
    "coupon_discount":      1,
    "credit_note_applied":  1,
    "credit_note_voided":   0,
    "payment_received":     1,
    "payment_failed":       0,
    "balance_adjustment":   0,  # can be either
    "transfer_in":          1,
    "transfer_out":        -1,
    "manual_correction":    0,  # can be either
}

BLOCK_TYPES = frozenset(BLOCK_SIGN.keys())


def _validate_amount_sign(block_type: str, amount_cents: int):
    """Ensure amount sign matches block type semantics."""
    expected = BLOCK_SIGN.get(block_type, 0)
    if expected == 0:
        return  # neutral types accept any sign
    if expected == 1 and amount_cents < 0:
        raise ValidationError(
            f"Block type '{block_type}' requires non-negative amount, got {amount_cents}"
        )
    if expected == -1 and amount_cents > 0:
        raise ValidationError(
            f"Block type '{block_type}' requires non-positive amount, got {amount_cents}"
        )


def _compute_hash(block: dict) -> str:
    """Compute SHA-256 hash for a block."""
    # Normalize data: always use the JSON string form for consistent hashing
    data = block["data"]
    if isinstance(data, (dict, list)):
        data = json.dumps(data, sort_keys=True, separators=(",", ":"))

    payload = json.dumps({
        "index": block.get("idx", block.get("index", 0)),
        "prev_hash": block["prev_hash"],
        "timestamp": block["timestamp"],
        "block_type": block["block_type"],
        "user_id": block["user_id"],
        "amount_cents": block["amount_cents"],
        "balance_after_cents": block["balance_after_cents"],
        "resource_type": block["resource_type"],
        "resource_id": block["resource_id"],
        "data": data,
        "nonce": block["nonce"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


async def _get_last_block(user_id: str) -> dict | None:
    """Get the last block for a user's chain."""
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM ledger_blocks WHERE user_id = ? ORDER BY idx DESC LIMIT 1",
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return db.row_to_dict(dict(row))


async def _get_genesis_or_create(user_id: str) -> dict:
    """Get or create the genesis block for a user. Must be called under lock."""
    last = await _get_last_block(user_id)
    if last:
        return last

    genesis = {
        "id": f"blk_{secrets.token_hex(12)}",
        "user_id": user_id,
        "idx": 0,
        "prev_hash": "0" * 64,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block_type": "genesis",
        "amount_cents": 0,
        "balance_after_cents": 0,
        "resource_type": "user",
        "resource_id": user_id,
        "data": json.dumps({"event": "chain_created"}, sort_keys=True, separators=(",", ":")),
        "nonce": secrets.token_hex(8),
    }
    genesis["hash"] = _compute_hash(genesis)
    await db.insert("ledger_blocks", genesis)
    logger.info("Genesis block created for user %s", user_id)
    return genesis


async def append_block(
    user_id: str,
    block_type: str,
    amount_cents: int,
    balance_after_cents: int,
    resource_type: str = "",
    resource_id: str = "",
    data: dict | None = None,
) -> dict:
    """Append a new block to a user's ledger chain (serialized per user)."""
    _validate_user_id(user_id)

    if block_type not in BLOCK_TYPES:
        raise ValidationError(f"Invalid block type: {block_type}")

    if not isinstance(amount_cents, int):
        raise ValidationError("amount_cents must be an integer")
    if not isinstance(balance_after_cents, int):
        raise ValidationError("balance_after_cents must be an integer")
    if balance_after_cents < 0:
        raise ValidationError("balance_after_cents cannot be negative")

    _validate_amount_sign(block_type, amount_cents)

    if len(resource_type) > 64:
        raise ValidationError("resource_type too long")
    if len(resource_id) > 128:
        raise ValidationError("resource_id too long")

    # Serialize writes per user to prevent concurrent chain corruption
    lock = await _get_lock(user_id)
    async with lock:
        prev = await _get_genesis_or_create(user_id)

        block = {
            "id": f"blk_{secrets.token_hex(12)}",
            "user_id": user_id,
            "idx": prev["idx"] + 1,
            "prev_hash": prev["hash"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "block_type": block_type,
            "amount_cents": amount_cents,
            "balance_after_cents": balance_after_cents,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "data": json.dumps(data or {}, sort_keys=True, separators=(",", ":")),
            "nonce": secrets.token_hex(8),
        }
        block["hash"] = _compute_hash(block)
        await db.insert("ledger_blocks", block)

    logger.info(
        "Block #%d appended: %s %+d cents (bal=%d) user=%s",
        block["idx"], block_type, amount_cents,
        balance_after_cents, user_id,
    )
    return block


async def get_chain(user_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Get a user's ledger chain, newest first."""
    _validate_user_id(user_id)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM ledger_blocks WHERE user_id = ? ORDER BY idx DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )
    rows = await cursor.fetchall()
    return [db.row_to_dict(dict(r)) for r in rows]


async def get_chain_length(user_id: str) -> int:
    """Get total number of blocks in a user's chain."""
    _validate_user_id(user_id)
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT COUNT(*) FROM ledger_blocks WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def verify_chain(user_id: str) -> dict:
    """
    Verify the integrity of a user's entire ledger chain.
    Returns: {valid: bool, length: int, errors: [...]}
    """
    _validate_user_id(user_id)
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM ledger_blocks WHERE user_id = ? ORDER BY idx ASC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    blocks = [db.row_to_dict(dict(r)) for r in rows]

    if not blocks:
        return {"valid": True, "length": 0, "errors": []}

    errors = []

    # Check genesis
    if blocks[0]["idx"] != 0:
        errors.append({"block": 0, "error": "Missing genesis block"})
    if blocks[0]["prev_hash"] != "0" * 64:
        errors.append({"block": 0, "error": "Genesis prev_hash is not zero"})

    for i, block in enumerate(blocks):
        # Verify hash
        computed = _compute_hash(block)
        if computed != block["hash"]:
            errors.append({
                "block": block["idx"],
                "error": "Hash mismatch — block has been tampered with",
                "expected": computed,
                "stored": block["hash"],
            })

        # Verify chain linkage
        if i > 0:
            if block["prev_hash"] != blocks[i - 1]["hash"]:
                errors.append({
                    "block": block["idx"],
                    "error": "Chain broken — prev_hash does not match previous block",
                })
            if block["idx"] != blocks[i - 1]["idx"] + 1:
                errors.append({
                    "block": block["idx"],
                    "error": f"Index gap: expected {blocks[i - 1]['idx'] + 1}, got {block['idx']}",
                })

    return {
        "valid": len(errors) == 0,
        "length": len(blocks),
        "errors": errors,
    }


async def verify_all_chains() -> dict:
    """
    Verify all user chains. Used by fraud detection.
    Returns: {total_users, valid_count, invalid_count, corrupted_users: [...]}
    """
    d = await db.get_db()
    cursor = await d.execute("SELECT DISTINCT user_id FROM ledger_blocks")
    rows = await cursor.fetchall()
    user_ids = [r[0] for r in rows]

    valid_count = 0
    corrupted = []

    for uid in user_ids:
        result = await verify_chain(uid)
        if result["valid"]:
            valid_count += 1
        else:
            corrupted.append({
                "user_id": uid,
                "errors": result["errors"],
                "chain_length": result["length"],
            })

    return {
        "total_users": len(user_ids),
        "valid_count": valid_count,
        "invalid_count": len(corrupted),
        "corrupted_users": corrupted,
    }


async def get_balance_proof(user_id: str) -> dict:
    """
    Get cryptographic proof of current balance from the chain.
    Compares chain balance with user.balance and wallet balances.
    """
    _validate_user_id(user_id)

    last_block = await _get_last_block(user_id)
    if not last_block:
        return {
            "user_id": user_id,
            "chain_balance_cents": 0,
            "verified": True,
            "block_count": 0,
        }

    user = await db.fetch_one("users", id=user_id)
    user_balance_cents = user.get("balance_cents", 0) if user else 0

    # Sum wallet balances
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT SUM(balance_cents) FROM billing_wallets WHERE user_id = ? AND status = 'active'",
        (user_id,),
    )
    row = await cursor.fetchone()
    wallet_balance_cents = row[0] or 0

    total_recorded = user_balance_cents + wallet_balance_cents
    chain_balance = last_block["balance_after_cents"]

    return {
        "user_id": user_id,
        "chain_balance_cents": chain_balance,
        "user_balance_cents": user_balance_cents,
        "wallet_balance_cents": wallet_balance_cents,
        "total_recorded_cents": total_recorded,
        "discrepancy_cents": abs(chain_balance - total_recorded),
        "verified": chain_balance == total_recorded,
        "last_block_hash": last_block["hash"],
        "block_count": last_block["idx"] + 1,
    }


async def find_discrepancies() -> list[dict]:
    """
    Find all users where recorded balances don't match chain balances.
    Core fraud detection mechanism.
    """
    d = await db.get_db()
    cursor = await d.execute("SELECT DISTINCT user_id FROM ledger_blocks")
    rows = await cursor.fetchall()
    user_ids = [r[0] for r in rows]

    discrepancies = []
    for uid in user_ids:
        proof = await get_balance_proof(uid)
        if not proof["verified"]:
            discrepancies.append(proof)

    return discrepancies


async def get_global_stats() -> dict:
    """Get global ledger statistics."""
    d = await db.get_db()

    cursor = await d.execute("SELECT COUNT(*) FROM ledger_blocks")
    total_blocks = (await cursor.fetchone())[0]

    cursor = await d.execute("SELECT COUNT(DISTINCT user_id) FROM ledger_blocks")
    total_users = (await cursor.fetchone())[0]

    cursor = await d.execute(
        "SELECT block_type, COUNT(*), SUM(amount_cents) FROM ledger_blocks "
        "WHERE block_type != 'genesis' GROUP BY block_type"
    )
    by_type = {}
    for row in await cursor.fetchall():
        by_type[row[0]] = {"count": row[1], "total_cents": row[2] or 0}

    cursor = await d.execute(
        "SELECT SUM(amount_cents) FROM ledger_blocks WHERE amount_cents > 0 AND block_type != 'genesis'"
    )
    total_inflow = (await cursor.fetchone())[0] or 0

    cursor = await d.execute(
        "SELECT SUM(amount_cents) FROM ledger_blocks WHERE amount_cents < 0"
    )
    total_outflow = (await cursor.fetchone())[0] or 0

    return {
        "total_blocks": total_blocks,
        "total_users": total_users,
        "total_inflow_cents": total_inflow,
        "total_outflow_cents": total_outflow,
        "net_cents": total_inflow + total_outflow,
        "by_type": by_type,
    }
