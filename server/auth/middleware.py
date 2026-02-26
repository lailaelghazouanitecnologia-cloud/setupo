"""Auth middleware — resolves Bearer token to project context."""
import hashlib
import hmac
import logging
import os
import secrets

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from server.config import settings
from core import db

logger = logging.getLogger("setupo.auth")

security = HTTPBearer(auto_error=False)

_cached_admin_token: str | None = None


def _pbkdf2_verify(password: str, stored: str) -> bool:
    """Verify password against PBKDF2-SHA256 hash (same format as agent)."""
    if ":" not in stored:
        return False
    salt, hash_hex = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(dk.hex(), hash_hex)


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    role: str


def verify_password(email: str, password: str) -> dict | None:
    """Verify admin login. Supports PBKDF2 hash or plaintext from env."""
    admin_email = settings.ADMIN_EMAIL
    admin_password = settings.ADMIN_PASSWORD
    if not admin_email or not admin_password:
        logger.warning("Admin credentials not configured (SETUPO_ADMIN_EMAIL / SETUPO_ADMIN_PASSWORD)")
        return None
    if email != admin_email:
        return None
    # PBKDF2 hash format: "salt_hex:derived_key_hex" (always 97+ chars)
    if ":" in admin_password and len(admin_password) > 80:
        if not _pbkdf2_verify(password, admin_password):
            return None
    else:
        # Plaintext password — constant-time comparison
        if not hmac.compare_digest(password, admin_password):
            return None
    return {"email": admin_email, "role": "admin"}


def load_admin_token() -> str:
    global _cached_admin_token
    if _cached_admin_token:
        return _cached_admin_token
    token_path = str(settings.TOKEN_PATH)
    if os.path.exists(token_path):
        with open(token_path) as f:
            _cached_admin_token = f.read().strip()
    else:
        _cached_admin_token = secrets.token_urlsafe(64)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(_cached_admin_token)
        os.chmod(token_path, 0o600)
        logger.warning("Generated new admin token: %s...", _cached_admin_token[:16])
    return _cached_admin_token


PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/auth/login",
    "/api/capabilities",
    "/docs",
    "/openapi.json",
    "/redoc",
})


class AuthContext:
    """Resolved auth context — either admin or project-scoped."""

    def __init__(self, is_admin: bool = False, project_id: str | None = None):
        self.is_admin = is_admin
        self.project_id = project_id

    def require_project(self) -> str:
        if self.project_id:
            return self.project_id
        raise HTTPException(403, "This endpoint requires a project API key")


async def resolve_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext | None:
    """Resolve Bearer token to auth context.

    Supports:
    - Admin token (from /etc/setupo/token or generated)
    - Project API key (sk_live_xxxx)
    """
    if request.url.path in PUBLIC_PATHS:
        return None

    if not credentials:
        raise HTTPException(401, "Missing authorization token")

    token = credentials.credentials

    # Check admin token
    admin_token = load_admin_token()
    if secrets.compare_digest(token, admin_token):
        return AuthContext(is_admin=True)

    # Check project API key
    if token.startswith("sk_live_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        project = await db.fetch_one("projects", api_key_hash=key_hash)
        if project:
            return AuthContext(project_id=project["id"])

    logger.warning("Invalid token from %s on %s", request.client.host, request.url.path)
    raise HTTPException(401, "Invalid token or API key")
