"""Tests for auth — users, JWT, passwords."""
import pytest
from core import users
from core.errors import AuthError, ConflictError, ValidationError
from server.auth.jwt import (
    hash_password, verify_password,
    create_user_token, decode_user_token,
)


# ── Password hashing ─────────────────────────────────────────

def test_password_hash_and_verify():
    pw = "mySecureP@ss1"
    hashed = hash_password(pw)
    assert ":" in hashed
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_hash_unique_salt():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # Different salts


def test_verify_password_bad_format():
    assert verify_password("x", "no-colon-here") is False
    assert verify_password("x", "") is False


# ── JWT tokens ────────────────────────────────────────────────

def test_create_and_decode_token():
    token = create_user_token("user_abc123", "test@test.com", "user")
    assert token.startswith("usr_")

    payload = decode_user_token(token)
    assert payload is not None
    assert payload["sub"] == "user_abc123"
    assert payload["email"] == "test@test.com"
    assert payload["role"] == "user"


def test_decode_invalid_token():
    assert decode_user_token("usr_garbage.garbage.garbage") is None
    assert decode_user_token("not_a_token") is None
    assert decode_user_token("") is None


def test_decode_tampered_token():
    token = create_user_token("user_abc123", "test@test.com")
    # Tamper with payload
    parts = token[4:].split(".")
    parts[1] = parts[1][::-1]
    tampered = "usr_" + ".".join(parts)
    assert decode_user_token(tampered) is None


# ── User creation ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user(fresh_db):
    user = await users.create_user("new@test.com", "pass1234", "New User")
    assert user["email"] == "new@test.com"
    assert user["name"] == "New User"
    assert user["role"] == "user"
    assert user["id"].startswith("user_")


@pytest.mark.asyncio
async def test_create_user_duplicate_email(fresh_db):
    await users.create_user("dup@test.com", "pass1234")
    with pytest.raises(ConflictError):
        await users.create_user("dup@test.com", "pass45678")


@pytest.mark.asyncio
async def test_create_user_invalid_email(fresh_db):
    with pytest.raises(ValidationError):
        await users.create_user("not-an-email", "pass1234")


@pytest.mark.asyncio
async def test_create_user_short_password(fresh_db):
    with pytest.raises(ValidationError):
        await users.create_user("ok@test.com", "12")


@pytest.mark.asyncio
async def test_create_user_default_name(fresh_db):
    """If no name, defaults to email username."""
    user = await users.create_user("auto@domain.com", "pass1234")
    assert user["name"] == "auto"


# ── Authentication ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticate_success(fresh_db):
    await users.create_user("auth@test.com", "correct1234", "Auth")
    user = await users.authenticate("auth@test.com", "correct1234")
    assert user["email"] == "auth@test.com"


@pytest.mark.asyncio
async def test_authenticate_wrong_password(fresh_db):
    await users.create_user("auth2@test.com", "correct1234")
    with pytest.raises(AuthError):
        await users.authenticate("auth2@test.com", "wrong")


@pytest.mark.asyncio
async def test_authenticate_nonexistent(fresh_db):
    with pytest.raises(AuthError):
        await users.authenticate("ghost@test.com", "pass1234")


# ── Profile updates ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_profile_name(test_user):
    updated = await users.update_profile(test_user["id"], name="New Name")
    assert updated["name"] == "New Name"


@pytest.mark.asyncio
async def test_update_profile_email(test_user):
    updated = await users.update_profile(test_user["id"], email="new@test.com")
    assert updated["email"] == "new@test.com"


@pytest.mark.asyncio
async def test_change_password(test_user):
    await users.change_password(test_user["id"], "password1234", "newpass1234")
    # Old password should fail
    with pytest.raises(AuthError):
        await users.authenticate(test_user["email"], "password1234")
    # New password should work
    user = await users.authenticate(test_user["email"], "newpass1234")
    assert user["email"] == test_user["email"]


@pytest.mark.asyncio
async def test_change_password_wrong_current(test_user):
    with pytest.raises(AuthError):
        await users.change_password(test_user["id"], "wrong", "newpass")


# ── Subdomain ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claim_subdomain(test_user):
    sub = await users.claim_subdomain(test_user["id"], "myapp")
    assert sub == "myapp"


@pytest.mark.asyncio
async def test_claim_reserved_subdomain(test_user):
    with pytest.raises(ConflictError):
        await users.claim_subdomain(test_user["id"], "admin")


@pytest.mark.asyncio
async def test_claim_invalid_subdomain(test_user):
    with pytest.raises(ValidationError):
        await users.claim_subdomain(test_user["id"], "A")  # too short, uppercase


@pytest.mark.asyncio
async def test_check_subdomain_available(fresh_db):
    available = await users.check_subdomain_available("fresh-name")
    assert available is True


# ── Token issuance ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issue_token(test_user):
    token = users.issue_token(test_user)
    payload = decode_user_token(token)
    assert payload is not None
    assert payload["sub"] == test_user["id"]
    assert payload["email"] == test_user["email"]
