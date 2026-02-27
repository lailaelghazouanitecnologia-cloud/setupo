"""User JWT — HMAC-based tokens for registered users."""
import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

JWT_SECRET = os.environ.get("SETUPO_JWT_SECRET", secrets.token_hex(32))
JWT_EXPIRY = 86400 * 7  # 7 days

# User token prefix to distinguish from admin tokens and API keys
USER_TOKEN_PREFIX = "usr_"


def _b64encode_json(data: dict) -> str:
    return urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def _b64decode_json(s: str) -> dict:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return json.loads(urlsafe_b64decode(s))


def hash_password(password: str) -> str:
    """Hash password with PBKDF2-SHA256."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against PBKDF2-SHA256 hash."""
    if ":" not in stored:
        return False
    salt, hash_hex = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(dk.hex(), hash_hex)


def create_user_token(user_id: str, email: str, role: str = "user") -> str:
    """Create a JWT for a registered user."""
    header = _b64encode_json({"alg": "HS256", "typ": "JWT"})
    payload = _b64encode_json({
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY,
    })
    signing_input = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    signature = urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{USER_TOKEN_PREFIX}{header}.{payload}.{signature}"


def decode_user_token(token: str) -> dict | None:
    """Verify and decode a user JWT. Returns payload or None."""
    if not token.startswith(USER_TOKEN_PREFIX):
        return None
    token = token[len(USER_TOKEN_PREFIX):]
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
