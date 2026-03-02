import hashlib
import hmac
import logging
import os
import secrets

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from server.config import settings
from server.auth.jwt import decode_user_token, verify_password as _pbkdf2_verify
from server.core import db

logger = logging.getLogger("nso.auth")

security = HTTPBearer(auto_error=False)

_cached_admin_token: str | None = None

PBKDF2_MIN_LENGTH = 80


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    role: str


def verify_password(email: str, password: str) -> dict | None:
    admin_email = settings.ADMIN_EMAIL
    admin_password = settings.ADMIN_PASSWORD

    if not admin_email or not admin_password:
        return None
    if email != admin_email:
        return None

    is_hashed = ":" in admin_password and len(admin_password) > PBKDF2_MIN_LENGTH
    if is_hashed:
        if not _pbkdf2_verify(password, admin_password):
            return None
    elif not hmac.compare_digest(password, admin_password):
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
        return _cached_admin_token

    _cached_admin_token = secrets.token_urlsafe(64)
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        f.write(_cached_admin_token)
    os.chmod(token_path, 0o600)
    logger.warning("Generated new admin token — saved to %s", token_path)
    return _cached_admin_token


PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/verify-email",
    "/api/auth/resend-verification",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/capabilities",
    "/api/billing/plans",
    "/api/billing/stripe/webhook",
    "/docs",
    "/openapi.json",
    "/redoc",
})

PUBLIC_PREFIXES = (
    "/api/modules/catalog",
)


class AuthContext:
    def __init__(
        self,
        is_admin: bool = False,
        project_id: str | None = None,
        user_id: str | None = None,
        user_email: str | None = None,
        user_role: str | None = None,
    ):
        self.is_admin = is_admin
        self.project_id = project_id
        self.user_id = user_id
        self.user_email = user_email
        self.user_role = user_role or ("admin" if is_admin else None)

    def require_project(self) -> str:
        if self.project_id:
            return self.project_id
        raise HTTPException(403, "This endpoint requires a project API key")


async def resolve_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext | None:
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return None

    if not credentials:
        raise HTTPException(401, "Missing authorization token")

    token = credentials.credentials

    if token.startswith("usr_"):
        payload = decode_user_token(token)
        if not payload:
            raise HTTPException(401, "Invalid or expired user token")
        return AuthContext(
            user_id=payload["sub"],
            user_email=payload.get("email"),
            user_role=payload.get("role", "user"),
            is_admin=payload.get("role") == "admin",
        )

    admin_token = load_admin_token()
    if secrets.compare_digest(token, admin_token):
        return AuthContext(is_admin=True)

    if token.startswith("sk_live_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        project = await db.fetch_one("projects", api_key_hash=key_hash)
        if project:
            return AuthContext(project_id=project["id"])

    client_ip = getattr(request.client, "host", "unknown") if request.client else "unknown"
    logger.warning("Invalid token from %s on %s", client_ip, request.url.path)
    raise HTTPException(401, "Invalid token or API key")
