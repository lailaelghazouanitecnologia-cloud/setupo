"""Tests for core/billing.py — plans, subscriptions, coupons, wallets, invoices."""
import pytest
from server.core import billing
from server.core.errors import ConflictError, NotFoundError, ValidationError


# ── Plans ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_default_plans(fresh_db):
    plans = await billing.list_plans()
    assert len(plans) == 4
    codes = [p["code"] for p in plans]
    assert "free" in codes
    assert "starter" in codes
    assert "pro" in codes
    assert "scale" in codes


@pytest.mark.asyncio
async def test_get_plan(fresh_db):
    plan = await billing.get_plan("free")
    assert plan["code"] == "free"
    assert plan["amount_cents"] == 0


@pytest.mark.asyncio
async def test_get_plan_not_found(fresh_db):
    with pytest.raises(NotFoundError):
        await billing.get_plan("nonexistent")


@pytest.mark.asyncio
async def test_plans_sorted_by_price(fresh_db):
    plans = await billing.list_plans()
    prices = [p["amount_cents"] for p in plans]
    assert prices == sorted(prices)


# ── Subscriptions ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_subscription(fresh_db, test_user):
    sub = await billing.create_subscription(test_user["id"], "free")
    assert sub["plan_code"] == "free"
    assert sub["status"] == "active"
    assert sub["user_id"] == test_user["id"]


@pytest.mark.asyncio
async def test_create_trial_subscription(fresh_db, test_user):
    sub = await billing.create_subscription(test_user["id"], "starter", trial=True)
    assert sub["status"] == "trialing"


@pytest.mark.asyncio
async def test_duplicate_subscription_rejected(fresh_db, test_user):
    await billing.create_subscription(test_user["id"], "free")
    with pytest.raises(ConflictError):
        await billing.create_subscription(test_user["id"], "free")


@pytest.mark.asyncio
async def test_upgrade_subscription(fresh_db, test_user):
    await billing.create_subscription(test_user["id"], "free")
    new_sub = await billing.create_subscription(test_user["id"], "starter")
    assert new_sub["plan_code"] == "starter"
    assert new_sub["status"] in ("active", "trialing")


@pytest.mark.asyncio
async def test_cancel_subscription(fresh_db, test_user):
    await billing.create_subscription(test_user["id"], "free")
    cancelled = await billing.cancel_subscription(test_user["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_at"] is not None


@pytest.mark.asyncio
async def test_pause_resume_subscription(fresh_db, test_user):
    await billing.create_subscription(test_user["id"], "free")
    paused = await billing.pause_subscription(test_user["id"])
    assert paused["status"] == "paused"
    resumed = await billing.resume_subscription(test_user["id"])
    assert resumed["status"] == "active"


@pytest.mark.asyncio
async def test_cancel_nonexistent_subscription(fresh_db, test_user):
    with pytest.raises(NotFoundError):
        await billing.cancel_subscription(test_user["id"])


# ── Coupons ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_coupon(fresh_db):
    coupon = await billing.create_coupon(
        code="SAVE20", name="20% Off", coupon_type="percentage", value=20,
    )
    assert coupon["code"] == "SAVE20"
    assert coupon["value"] == 20
    assert coupon["active"] is True


@pytest.mark.asyncio
async def test_create_coupon_duplicate(fresh_db):
    await billing.create_coupon(code="DUP", name="Dup", value=10)
    with pytest.raises(ConflictError):
        await billing.create_coupon(code="DUP", name="Dup2", value=20)


@pytest.mark.asyncio
async def test_coupon_percentage_validation(fresh_db):
    with pytest.raises(ValidationError):
        await billing.create_coupon(code="BAD", name="Bad", coupon_type="percentage", value=150)


@pytest.mark.asyncio
async def test_apply_coupon(fresh_db, test_user):
    await billing.create_coupon(code="APPLY10", name="10%", value=10)
    sub = await billing.create_subscription(test_user["id"], "starter")
    applied = await billing.apply_coupon(test_user["id"], "APPLY10", sub["id"])
    assert applied["status"] == "active"


@pytest.mark.asyncio
async def test_apply_coupon_twice_rejected(fresh_db, test_user):
    await billing.create_coupon(code="ONCE", name="Once", value=10)
    await billing.apply_coupon(test_user["id"], "ONCE")
    with pytest.raises(ConflictError):
        await billing.apply_coupon(test_user["id"], "ONCE")


@pytest.mark.asyncio
async def test_deactivate_coupon(fresh_db):
    await billing.create_coupon(code="OFF", name="Off", value=5)
    deactivated = await billing.deactivate_coupon("OFF")
    assert deactivated["active"] is False


@pytest.mark.asyncio
async def test_apply_inactive_coupon_rejected(fresh_db, test_user):
    await billing.create_coupon(code="DEAD", name="Dead", value=10)
    await billing.deactivate_coupon("DEAD")
    with pytest.raises(ValidationError):
        await billing.apply_coupon(test_user["id"], "DEAD")


# ── Credit Notes ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_credit_note(fresh_db, test_user):
    cn = await billing.create_credit_note(
        user_id=test_user["id"], total_cents=500, reason="Refund test",
    )
    assert cn["total_cents"] == 500
    assert cn["balance_cents"] == 500
    assert cn["status"] == "available"


@pytest.mark.asyncio
async def test_credit_note_zero_rejected(fresh_db, test_user):
    with pytest.raises(ValidationError):
        await billing.create_credit_note(user_id=test_user["id"], total_cents=0)


@pytest.mark.asyncio
async def test_void_credit_note(fresh_db, test_user):
    cn = await billing.create_credit_note(
        user_id=test_user["id"], total_cents=500, reason="Test",
    )
    voided = await billing.void_credit_note(cn["id"])
    assert voided["status"] == "voided"


# ── Billable Metrics ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_billable_metric(fresh_db):
    m = await billing.create_billable_metric(
        code="api_calls", name="API Calls", aggregation_type="count",
    )
    assert m["code"] == "api_calls"
    assert m["aggregation_type"] == "count"


@pytest.mark.asyncio
async def test_create_metric_duplicate(fresh_db):
    await billing.create_billable_metric(code="dup_metric", name="Dup")
    with pytest.raises(ConflictError):
        await billing.create_billable_metric(code="dup_metric", name="Dup2")


@pytest.mark.asyncio
async def test_invalid_aggregation_type(fresh_db):
    with pytest.raises(ValidationError):
        await billing.create_billable_metric(
            code="bad", name="Bad", aggregation_type="invalid",
        )


# ── Usage Events ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_usage(fresh_db, test_user):
    event_id = await billing.record_usage(
        user_id=test_user["id"], metric="api_calls", units=5.0,
    )
    assert event_id.startswith("evt_")


@pytest.mark.asyncio
async def test_usage_idempotency(fresh_db, test_user):
    id1 = await billing.record_usage(
        user_id=test_user["id"], metric="api_calls", units=1.0,
        transaction_id="txn_001",
    )
    id2 = await billing.record_usage(
        user_id=test_user["id"], metric="api_calls", units=1.0,
        transaction_id="txn_001",
    )
    assert id1 == id2  # Same transaction_id returns same event


@pytest.mark.asyncio
async def test_usage_summary(fresh_db, test_user):
    await billing.create_billable_metric(code="storage", name="Storage", aggregation_type="sum")
    await billing.record_usage(test_user["id"], "storage", 10.0)
    await billing.record_usage(test_user["id"], "storage", 5.0)

    summary = await billing.get_usage_summary(
        test_user["id"], "2000-01-01", "2099-12-31",
    )
    assert summary.get("storage", 0) == 15.0


# ── Billing Events ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_billing_events_logged(fresh_db, test_user):
    await billing.create_subscription(test_user["id"], "free")
    events = await billing.list_billing_events(user_id=test_user["id"])
    assert len(events) >= 1
    types = [e["event_type"] for e in events]
    assert "subscription.created" in types
