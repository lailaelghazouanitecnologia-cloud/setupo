"""Token-based authentication for the Setupo API.
Token is generated at boot time and stored in /etc/setupo/token
"""
import os
import secrets
import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("setupo.auth")

TOKEN_PATH = "/etc/setupo/token"


def load_token() -> str:
    """Load the API token from disk, or generate one if missing."""
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            return f.read().strip()

    # Generate token if it doesn't exist (dev mode)
    token = secrets.token_urlsafe(64)
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(token)
    os.chmod(TOKEN_PATH, 0o600)
    logger.warning("Generated new API token (dev mode): %s", token[:12] + "...")
    return token


_cached_token: str | None = None


def get_token() -> str:
    global _cached_token
    if _cached_token is None:
        _cached_token = load_token()
    return _cached_token


def verify_token(authorization: str | None) -> bool:
    if not authorization:
        return False
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        return False
    return secrets.compare_digest(parts[1], get_token())


# Paths that don't require authentication
PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Public paths and dashboard static files
    if path in PUBLIC_PATHS or not path.startswith("/api"):
        return await call_next(request)

    # Health endpoint is public
    if path == "/api/health":
        return await call_next(request)

    # Verify token
    auth_header = request.headers.get("Authorization")
    if not verify_token(auth_header):
        logger.warning("Unauthorized request to %s from %s", path, request.client.host)
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": "Invalid or missing token"},
        )

    return await call_next(request)
