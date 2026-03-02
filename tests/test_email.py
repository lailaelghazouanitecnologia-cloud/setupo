"""Tests for core/email.py — tokens, verification, reset."""
import time
import pytest
from server.core import email as email_service
from server.core.errors import ValidationError


# ── Token generation & verification ───────────────────────────

def test_generate_and_verify_token():
    token = email_service._generate_token("user_abc123", "verify", 3600)
    result = email_service._verify_token(token, "verify")
    assert result == "user_abc123"


def test_token_wrong_purpose():
    token = email_service._generate_token("user_abc123", "verify", 3600)
    result = email_service._verify_token(token, "reset")
    assert result is None


def test_token_expired():
    token = email_service._generate_token("user_abc123", "verify", -1)
    result = email_service._verify_token(token, "verify")
    assert result is None


def test_token_tampered():
    token = email_service._generate_token("user_abc123", "verify", 3600)
    # Tamper with signature
    parts = token.split(":")
    parts[-1] = "a" * 32
    tampered = ":".join(parts)
    result = email_service._verify_token(tampered, "verify")
    assert result is None


def test_token_garbage():
    assert email_service._verify_token("garbage", "verify") is None
    assert email_service._verify_token("", "verify") is None
    assert email_service._verify_token("a:b", "verify") is None


# ── Email verification flow ───────────────────────────────────

@pytest.mark.asyncio
async def test_verify_email_flow(fresh_db, test_user):
    """Full flow: send verification → confirm."""
    # Send (won't actually send without SMTP)
    await email_service.send_verification_email(test_user["id"], test_user["email"])

    # Get the token from DB
    from server.core import db
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT token_hash FROM email_tokens WHERE user_id = ? AND purpose = 'verify'",
        (test_user["id"],),
    )
    row = await cursor.fetchone()
    assert row is not None  # Token was stored

    # Now generate a valid token manually and confirm
    token = email_service._generate_token(test_user["id"], "verify", 3600)
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    import secrets
    await db.insert("email_tokens", {
        "id": f"et_{secrets.token_hex(8)}",
        "user_id": test_user["id"],
        "token_hash": token_hash,
        "purpose": "verify",
        "used": 0,
        "expires_at": "2099-12-31T00:00:00",
        "created_at": "2026-01-01T00:00:00",
    })

    user_id = await email_service.confirm_verification(token)
    assert user_id == test_user["id"]

    # Check user is now verified
    user = await db.fetch_one("users", id=test_user["id"])
    assert user["verified"] == 1 or user["verified"] is True


@pytest.mark.asyncio
async def test_verify_token_reuse_rejected(fresh_db, test_user):
    """A verification token can only be used once."""
    from server.core import db
    import hashlib, secrets

    token = email_service._generate_token(test_user["id"], "verify", 3600)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await db.insert("email_tokens", {
        "id": f"et_{secrets.token_hex(8)}",
        "user_id": test_user["id"],
        "token_hash": token_hash,
        "purpose": "verify",
        "used": 0,
        "expires_at": "2099-12-31T00:00:00",
        "created_at": "2026-01-01T00:00:00",
    })

    await email_service.confirm_verification(token)  # First use: ok
    with pytest.raises(ValidationError):
        await email_service.confirm_verification(token)  # Second use: fail


# ── Password reset flow ───────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_password_flow(fresh_db, test_user):
    """Full flow: forgot → confirm reset → login with new password."""
    from server.core import db, users
    import hashlib, secrets as sec

    # Generate reset token manually
    token = email_service._generate_token(test_user["id"], "reset", 3600)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await db.insert("email_tokens", {
        "id": f"et_{sec.token_hex(8)}",
        "user_id": test_user["id"],
        "token_hash": token_hash,
        "purpose": "reset",
        "used": 0,
        "expires_at": "2099-12-31T00:00:00",
        "created_at": "2026-01-01T00:00:00",
    })

    # Reset password
    user_id = await email_service.confirm_reset(token, "newpassword1234")
    assert user_id == test_user["id"]

    # Old password should fail
    from server.core.errors import AuthError
    with pytest.raises(AuthError):
        await users.authenticate(test_user["email"], "password1234")

    # New password should work
    user = await users.authenticate(test_user["email"], "newpassword1234")
    assert user["email"] == test_user["email"]


@pytest.mark.asyncio
async def test_reset_short_password_rejected(fresh_db, test_user):
    """Reset with too-short password should fail."""
    from server.core import db
    import hashlib, secrets as sec

    token = email_service._generate_token(test_user["id"], "reset", 3600)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await db.insert("email_tokens", {
        "id": f"et_{sec.token_hex(8)}",
        "user_id": test_user["id"],
        "token_hash": token_hash,
        "purpose": "reset",
        "used": 0,
        "expires_at": "2099-12-31T00:00:00",
        "created_at": "2026-01-01T00:00:00",
    })

    with pytest.raises(ValidationError):
        await email_service.confirm_reset(token, "ab")


@pytest.mark.asyncio
async def test_reset_invalid_token(fresh_db):
    """Invalid reset token should fail."""
    with pytest.raises(ValidationError):
        await email_service.confirm_reset("garbage:token:0:fake", "newpass123")


@pytest.mark.asyncio
async def test_send_reset_unknown_email_silent(fresh_db):
    """Requesting reset for unknown email should succeed silently."""
    result = await email_service.send_reset_email("ghost@nowhere.com")
    assert result is True  # No error revealed
