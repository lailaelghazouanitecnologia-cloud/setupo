"""
z86 user management — registration, login, JWT tokens.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from z86 import db
from z86.config import settings

logger = logging.getLogger("z86.users")

# JWT secret — auto-generated if not set
_JWT_SECRET = os.environ.get("Z86_JWT_SECRET", "")
if not _JWT_SECRET:
    _JWT_SECRET = secrets.token_hex(32)
    logger.warning("Z86_JWT_SECRET not set — generated ephemeral secret")

_TOKEN_EXPIRY = 7 * 24 * 3600  # 7 days

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


# ── Password hashing (PBKDF2-SHA256) ────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ── JWT ──────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_token(user_id: str, email: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_EXPIRY,
    }).encode())
    sig_input = f"{header}.{payload}"
    sig = _b64url_encode(hmac.new(_JWT_SECRET.encode(), sig_input.encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        expected = _b64url_encode(
            hmac.new(_JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


# ── User CRUD ────────────────────────────────────────────

async def create_user(email: str, password: str, name: str = "") -> dict:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    existing = await db.fetch_one("users", email=email)
    if existing:
        raise HTTPException(409, "Email already registered")
    user_id = f"z86u_{secrets.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()
    await db.insert("users", {
        "id": user_id,
        "email": email,
        "name": name.strip(),
        "password_hash": hash_password(password),
        "plan": "free",
        "storage_limit": 1 * 1024 * 1024 * 1024,  # 1GB
        "created_at": now,
        "updated_at": now,
    })
    logger.info("User created: %s (%s)", user_id, email)
    return {"id": user_id, "email": email, "name": name.strip(), "plan": "free"}


async def authenticate(email: str, password: str) -> dict:
    email = email.strip().lower()
    user = await db.fetch_one("users", email=email)
    # constant-time: always verify even if user doesn't exist
    dummy = hash_password("dummy")
    stored = user["password_hash"] if user else dummy
    valid = verify_password(password, stored)
    if not user or not valid:
        raise HTTPException(401, "Invalid email or password")
    return _sanitize(user)


def issue_token(user: dict) -> str:
    return create_token(user["id"], user["email"])


async def get_user(user_id: str) -> dict | None:
    user = await db.fetch_one("users", id=user_id)
    return _sanitize(user) if user else None


async def update_profile(user_id: str, name: str | None = None, email: str | None = None) -> dict:
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if name is not None:
        updates["name"] = name.strip()
    if email is not None:
        email = email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(400, "Invalid email")
        existing = await db.fetch_one("users", email=email)
        if existing and existing["id"] != user_id:
            raise HTTPException(409, "Email already in use")
        updates["email"] = email
    await db.update("users", "id", user_id, updates)
    return await get_user(user_id)


async def change_password(user_id: str, current: str, new_password: str):
    user = await db.fetch_one("users", id=user_id)
    if not user or not verify_password(current, user["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    if len(new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    await db.update("users", "id", user_id, {
        "password_hash": hash_password(new_password),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def _sanitize(user: dict) -> dict:
    u = dict(user)
    u.pop("password_hash", None)
    return u


# ── Request auth dependency ──────────────────────────────

async def require_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = auth[7:]
    data = decode_token(token)
    if not data:
        raise HTTPException(401, "Invalid or expired token")
    user = await get_user(data["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    return user
