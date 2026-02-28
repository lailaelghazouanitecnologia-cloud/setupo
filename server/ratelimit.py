"""
Rate limiting middleware — protects auth endpoints from brute-force.

Uses in-memory sliding window per IP. Resets on server restart which
is acceptable since attackers must restart their attack too.
"""
import time
import logging
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("setupo.ratelimit")

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

# path -> { ip -> [timestamps] }
_buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))


def _get_client_ip(request: Request) -> str:
    """Get real client IP, respecting X-Forwarded-For behind nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_rate_limited(path: str, ip: str) -> bool:
    """Check if request should be rate limited."""
    config = RATE_LIMITS.get(path)
    if not config:
        return False

    max_requests, window = config
    now = time.monotonic()
    bucket = _buckets[path][ip]

    # Prune old entries
    cutoff = now - window
    _buckets[path][ip] = [t for t in bucket if t > cutoff]
    bucket = _buckets[path][ip]

    if len(bucket) >= max_requests:
        return True

    bucket.append(now)
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)

        path = request.url.path
        if path not in RATE_LIMITS:
            return await call_next(request)

        ip = _get_client_ip(request)
        if _is_rate_limited(path, ip):
            config = RATE_LIMITS[path]
            logger.warning("Rate limited: %s on %s (%d/%ds)", ip, path, config[0], config[1])
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests. Please try again later."},
                headers={"Retry-After": str(config[1])},
            )

        return await call_next(request)
