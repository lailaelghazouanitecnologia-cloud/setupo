import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

def _get_jwt_secret() -> str:
    """Get JWT secret from env, file, or generate and persist one."""
    env_secret = os.environ.get("NSO_JWT_SECRET", "")
    if env_secret:
        return env_secret
    # Persist to file so tokens survive restarts
    secret_file = os.path.join(os.environ.get("NSO_DATA_DIR", "/opt/nso/data"), ".jwt_secret")
    try:
        if os.path.isfile(secret_file):
            return open(secret_file).read().strip()
    except Exception:
        pass
    new_secret = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(secret_file), exist_ok=True)
        with open(secret_file, "w") as f:
            f.write(new_secret)
    except Exception:
        pass
    return new_secret

JWT_SECRET = _get_jwt_secret()
TOKEN_EXPIRY_SECONDS = 86400 * 7
USER_TOKEN_PREFIX = "usr_"
PBKDF2_ITERATIONS = 100_000


def _b64encode_json(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode_json(s: str) -> dict:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return json.loads(urlsafe_b64decode(s))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"{salt}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt, hash_hex = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)


def create_user_token(user_id: str, email: str, role: str = "user") -> str:
    now = int(time.time())
    header = _b64encode_json({"alg": "HS256", "typ": "JWT"})
    payload = _b64encode_json({
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + TOKEN_EXPIRY_SECONDS,
    })
    signing_input = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    signature = urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{USER_TOKEN_PREFIX}{header}.{payload}.{signature}"


def decode_user_token(token: str) -> dict | None:
    if not token.startswith(USER_TOKEN_PREFIX):
        return None

    raw = token[len(USER_TOKEN_PREFIX):]
    try:
        parts = raw.split(".")
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
