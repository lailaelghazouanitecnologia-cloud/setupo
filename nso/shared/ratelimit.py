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

# path -> { ip -> [timestamps] }
_buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

# Safety caps: prevent memory growth from many unique IPs
_MAX_IPS_PER_PATH = 10_000
_CLEANUP_INTERVAL = 300  # 5 minutes
_last_cleanup = time.monotonic()


def _get_client_ip(request: Request) -> str:
    """Get real client IP, respecting X-Forwarded-For behind nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _cleanup_stale_buckets():
    """Remove IPs with no recent activity. Runs periodically."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now

    removed = 0
    for path, ip_map in list(_buckets.items()):
        config = RATE_LIMITS.get(path)
        if not config:
            continue
        _, window = config
        cutoff = now - window
        for ip in list(ip_map.keys()):
            if not ip_map[ip] or ip_map[ip][-1] < cutoff:
                del ip_map[ip]
                removed += 1
    if removed:
        logger.debug("Rate limit cleanup: removed %d stale IP entries", removed)


def _is_rate_limited(path: str, ip: str) -> bool:
    """Check if request should be rate limited."""
    config = RATE_LIMITS.get(path)
    if not config:
        return False

    max_requests, window = config
    now = time.monotonic()

    # Periodic cleanup of stale entries
    _cleanup_stale_buckets()

    # Cap IPs per path to prevent memory exhaustion from DDoS
    ip_map = _buckets[path]
    if len(ip_map) >= _MAX_IPS_PER_PATH and ip not in ip_map:
        logger.warning("Rate limit bucket full for %s (%d IPs), rejecting new IP %s", path, len(ip_map), ip)
        return True

    bucket = ip_map[ip]

    # Prune old entries
    cutoff = now - window
    ip_map[ip] = [t for t in bucket if t > cutoff]
    bucket = ip_map[ip]

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
