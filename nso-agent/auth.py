import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("nso-agent.auth")

ADMIN_EMAIL = os.environ.get("NSO_ADMIN_EMAIL", "admin@setupo.dev")
ADMIN_PASSWORD_HASH = os.environ.get("NSO_ADMIN_PASSWORD_HASH", "")

JWT_SECRET = os.environ.get("NSO_JWT_SECRET", secrets.token_hex(32))
JWT_EXPIRY_SECONDS = 86400 * 7
PBKDF2_ITERATIONS = 100_000


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"{salt}:{dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt, hash_hex = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)


_DEFAULT_HASH = _hash_password("zarnlok4123")


def get_password_hash() -> str:
    return ADMIN_PASSWORD_HASH or _DEFAULT_HASH


def _b64encode_json(data: dict) -> str:
    return urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def _b64decode_json(s: str) -> dict:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return json.loads(urlsafe_b64decode(s))


def create_token(email: str) -> str:
    header = _b64encode_json({"alg": "HS256", "typ": "JWT"})
    payload = _b64encode_json({
        "sub": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    })
    signing_input = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    signature = urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"


def verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
        expected_b64 = urlsafe_b64encode(expected_sig).decode().rstrip("=")
        if not hmac.compare_digest(sig_b64, expected_b64):
            return None
        payload = _b64decode_json(payload_b64)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    role: str = "admin"


class AdminUser(BaseModel):
    email: str
    role: str = "admin"

BEARER_PREFIX_LEN = 7


async def require_admin(request: Request) -> AdminUser:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    token = auth_header[BEARER_PREFIX_LEN:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")

    return AdminUser(email=payload["sub"])

def authenticate(email: str, password: str) -> Optional[str]:
    if email != ADMIN_EMAIL:
        return None
    if not _verify_password(password, get_password_hash()):
        return None
    logger.info("Admin login: %s", email)
    return create_token(email)
