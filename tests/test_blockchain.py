"""Tests for core/blockchain.py — immutable ledger."""
import pytest
from nso.engine.admin import ledger as blockchain


@pytest.mark.asyncio
async def test_genesis_block_created(fresh_db, user_id):
    """First block for a user should be genesis."""
    block = await blockchain.append_block(
        user_id=user_id,
        block_type="wallet_topup",
        amount_cents=1000,
        balance_after_cents=1000,
        resource_type="wallet",
        resource_id="wal_test",
    )
    assert block["idx"] == 1  # genesis is 0, this is 1
    assert block["block_type"] == "wallet_topup"
    assert block["amount_cents"] == 1000
    assert block["balance_after_cents"] == 1000
    assert len(block["hash"]) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_chain_linkage(fresh_db, user_id):
    """Each block's prev_hash must match the previous block's hash."""
    b1 = await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=500, balance_after_cents=500,
    )
    b2 = await blockchain.append_block(
        user_id=user_id, block_type="invoice_charge",
        amount_cents=-200, balance_after_cents=300,
    )
    assert b2["prev_hash"] == b1["hash"]
    assert b2["idx"] == b1["idx"] + 1


@pytest.mark.asyncio
async def test_verify_chain_valid(fresh_db, user_id):
    """A valid chain should pass verification."""
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=1000, balance_after_cents=1000,
    )
    await blockchain.append_block(
        user_id=user_id, block_type="invoice_charge",
        amount_cents=-300, balance_after_cents=700,
    )
    result = await blockchain.verify_chain(user_id)
    assert result["valid"] is True
    assert result["length"] == 3  # genesis + 2
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_verify_chain_detects_tampering(fresh_db, user_id):
    """Modifying a block's data should break the chain."""
    from nso.shared import db
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=1000, balance_after_cents=1000,
    )
    b2 = await blockchain.append_block(
        user_id=user_id, block_type="invoice_charge",
        amount_cents=-300, balance_after_cents=700,
    )
    # Tamper with the block
    d = await db.get_db()
    await d.execute(
        "UPDATE ledger_blocks SET amount_cents = -999 WHERE id = ?",
        (b2["id"],),
    )
    await d.commit()

    result = await blockchain.verify_chain(user_id)
    assert result["valid"] is False
    assert len(result["errors"]) > 0


@pytest.mark.asyncio
async def test_invalid_user_id_rejected(fresh_db):
    """Invalid user_id format should raise ValidationError."""
    from nso.shared.errors import ValidationError
    with pytest.raises(ValidationError):
        await blockchain.append_block(
            user_id="bad_id", block_type="wallet_topup",
            amount_cents=100, balance_after_cents=100,
        )


@pytest.mark.asyncio
async def test_invalid_block_type_rejected(fresh_db, user_id):
    """Unknown block type should raise ValidationError."""
    from nso.shared.errors import ValidationError
    with pytest.raises(ValidationError):
        await blockchain.append_block(
            user_id=user_id, block_type="fake_type",
            amount_cents=100, balance_after_cents=100,
        )


@pytest.mark.asyncio
async def test_amount_sign_validation(fresh_db, user_id):
    """Positive block types reject negative amounts and vice versa."""
    from nso.shared.errors import ValidationError
    # wallet_topup requires non-negative
    with pytest.raises(ValidationError):
        await blockchain.append_block(
            user_id=user_id, block_type="wallet_topup",
            amount_cents=-100, balance_after_cents=0,
        )
    # invoice_charge requires non-positive
    with pytest.raises(ValidationError):
        await blockchain.append_block(
            user_id=user_id, block_type="invoice_charge",
            amount_cents=100, balance_after_cents=100,
        )


@pytest.mark.asyncio
async def test_negative_balance_rejected(fresh_db, user_id):
    """balance_after_cents cannot be negative."""
    from nso.shared.errors import ValidationError
    with pytest.raises(ValidationError):
        await blockchain.append_block(
            user_id=user_id, block_type="invoice_charge",
            amount_cents=-500, balance_after_cents=-500,
        )


@pytest.mark.asyncio
async def test_get_chain(fresh_db, user_id):
    """get_chain returns blocks in reverse order (newest first)."""
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=100, balance_after_cents=100,
    )
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=200, balance_after_cents=300,
    )
    chain = await blockchain.get_chain(user_id)
    assert len(chain) == 3  # genesis + 2
    assert chain[0]["idx"] > chain[1]["idx"]  # newest first


@pytest.mark.asyncio
async def test_get_chain_length(fresh_db, user_id):
    """get_chain_length returns correct count."""
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=100, balance_after_cents=100,
    )
    length = await blockchain.get_chain_length(user_id)
    assert length == 2  # genesis + 1


@pytest.mark.asyncio
async def test_balance_proof(fresh_db, user_id):
    """get_balance_proof should report chain balance."""
    from nso.shared import db
    # Create user row
    await db.insert("users", {
        "id": user_id, "email": "proof@test.com",
        "password_hash": "x:y", "name": "Proof", "role": "user",
        "balance": 10.00, "verified": 0,
    })
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=1000, balance_after_cents=1000,
    )
    proof = await blockchain.get_balance_proof(user_id)
    assert proof["chain_balance_cents"] == 1000
    assert proof["user_balance_cents"] == 1000
    assert proof["verified"] is True


@pytest.mark.asyncio
async def test_global_stats(fresh_db, user_id):
    """get_global_stats returns aggregated data."""
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=500, balance_after_cents=500,
    )
    await blockchain.append_block(
        user_id=user_id, block_type="invoice_charge",
        amount_cents=-200, balance_after_cents=300,
    )
    stats = await blockchain.get_global_stats()
    assert stats["total_blocks"] == 3  # genesis + 2
    assert stats["total_users"] == 1
    assert stats["total_inflow_cents"] == 500
    assert stats["total_outflow_cents"] == -200


@pytest.mark.asyncio
async def test_verify_all_chains(fresh_db, user_id):
    """verify_all_chains should return valid results."""
    await blockchain.append_block(
        user_id=user_id, block_type="wallet_topup",
        amount_cents=100, balance_after_cents=100,
    )
    result = await blockchain.verify_all_chains()
    assert result["total_users"] == 1
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 0
