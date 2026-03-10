"""
Rate limiting middleware — protects auth endpoints from brute-force.

Uses Redis sliding window when available for distributed rate limiting
across multiple gateway nodes. Falls back to in-memory for single-node.
"""
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("nso.ratelimit")

# Config: (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login": (5, 60),               # 5 per minute
    "/api/auth/register": (3, 3600),           # 3 per hour
    "/api/auth/forgot-password": (3, 3600),    # 3 per hour
    "/api/auth/reset-password": (5, 3600),     # 5 per hour
    "/api/auth/resend-verification": (3, 3600),# 3 per hour
    "/api/auth/verify-email": (10, 3600),      # 10 per hour
    "/api/billing/topup": (5, 3600),           # 5 per hour
}

# Build-specific rate limit: 1 build per 60s per project (enforced in build service)
BUILD_RATE_LIMIT = (1, 60)


def _get_client_ip(request: Request) -> str:
    """Get real client IP, respecting X-Forwarded-For behind nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def _is_rate_limited(path: str, ip: str) -> bool:
    """Check if request should be rate limited using Redis distributed window."""
    config = RATE_LIMITS.get(path)
    if not config:
        return False

    max_requests, window = config
    from nso.shared.redis import check_rate_limit
    allowed = await check_rate_limit(f"rl:{path}:{ip}", max_requests, window)
    return not allowed


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)

        path = request.url.path
        if path not in RATE_LIMITS:
            return await call_next(request)

        ip = _get_client_ip(request)
        if await _is_rate_limited(path, ip):
            config = RATE_LIMITS[path]
            logger.warning("Rate limited: %s on %s (%d/%ds)", ip, path, config[0], config[1])
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests. Please try again later."},
                headers={"Retry-After": str(config[1])},
            )

        return await call_next(request)
