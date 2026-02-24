"""MMS Auth - Email/password + token-based API authentication."""
import hashlib
import os
import secrets
import logging

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger("mms.auth")

TOKEN_PATH = os.environ.get("MMS_TOKEN_PATH", "/etc/mms/token")
_cached_token: str | None = None

security = HTTPBearer(auto_error=False)

# Hardcoded users (hashed password for security in memory)
USERS = {
    "ayman_gha@hotmail.com": {
        "password_hash": hashlib.sha256("zarnlok4123".encode()).hexdigest(),
        "role": "admin",
    }
}


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    role: str


def verify_password(email: str, password: str) -> dict | None:
    user = USERS.get(email)
    if not user:
        return None
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    if not secrets.compare_digest(pw_hash, user["password_hash"]):
        return None
    return user


def load_token() -> str:
    """Load or generate the API token."""
    global _cached_token
    if _cached_token:
        return _cached_token

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            _cached_token = f.read().strip()
    else:
        _cached_token = secrets.token_urlsafe(64)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(_cached_token)
        os.chmod(TOKEN_PATH, 0o600)
        logger.warning("Generated new token: %s...", _cached_token[:16])

    return _cached_token


# Public endpoints that don't need auth
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/login", "/docs", "/openapi.json", "/redoc"})


async def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Dependency that validates the Bearer token."""
    if request.url.path in PUBLIC_PATHS:
        return None

    if not credentials:
        raise HTTPException(401, "Missing authorization token")

    if not secrets.compare_digest(credentials.credentials, load_token()):
        logger.warning("Invalid token from %s on %s", request.client.host, request.url.path)
        raise HTTPException(401, "Invalid token")

    return credentials.credentials
