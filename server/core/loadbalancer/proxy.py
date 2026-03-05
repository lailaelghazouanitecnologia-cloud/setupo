"""
LB Proxy — reverse proxy middleware that forwards requests through the load balancer.

On the admin instance, this intercepts API requests and forwards them to
backend servers based on LB rules. Admin routes are never proxied.
"""
import logging
from datetime import datetime

import httpx

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse, JSONResponse

from server.core.loadbalancer.router import resolve_backend

logger = logging.getLogger("nso.lb.proxy")

# Paths that should NEVER be proxied (handled locally on admin)
_LOCAL_PREFIXES = (
    "/api/admin",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Timeout for proxied requests
PROXY_TIMEOUT = 60.0
PROXY_CONNECT_TIMEOUT = 5.0


class LBProxyMiddleware(BaseHTTPMiddleware):
    """
    Intercepts incoming requests and proxies them to a backend
    selected by the load balancer. Only active when LB has rules defined.

    Skips:
    - /api/admin/* (always local)
    - /api/health (always local)
    - Requests where no LB rule matches
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Never proxy admin/local paths
        for prefix in _LOCAL_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Try to resolve a backend via LB rules
        client_ip = ""
        if request.client:
            client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host

        cookie_sid = request.cookies.get("NSO_LB_SID", "")

        try:
            backend = await resolve_backend(
                path=path,
                host=request.headers.get("host", ""),
                client_ip=client_ip,
                cookie_sid=cookie_sid,
            )
        except Exception as e:
            logger.error("LB resolve error: %s", e)
            return await call_next(request)

        if not backend:
            # No matching rule or no healthy backend — handle locally
            return await call_next(request)

        # Proxy the request to the selected backend
        return await self._proxy_request(request, backend)

    async def _proxy_request(self, request: Request, backend) -> Response:
        """Forward the request to the selected backend."""
        target_url = f"http://{backend.ip}:{backend.port}{request.url.path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        # Build headers (forward all except hop-by-hop)
        headers = dict(request.headers)
        headers.pop("host", None)
        headers["host"] = request.headers.get("host", "")
        headers["x-real-ip"] = request.client.host if request.client else ""
        headers["x-forwarded-for"] = request.client.host if request.client else ""
        headers["x-forwarded-proto"] = request.url.scheme
        headers["x-lb-backend"] = backend.id

        # Read body
        body = await request.body()

        try:
            timeout = httpx.Timeout(
                connect=PROXY_CONNECT_TIMEOUT,
                read=PROXY_TIMEOUT,
                write=PROXY_TIMEOUT,
                pool=PROXY_TIMEOUT,
            )

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                )

            # Build response headers (strip hop-by-hop)
            resp_headers = dict(resp.headers)
            for h in ("transfer-encoding", "connection", "keep-alive"):
                resp_headers.pop(h, None)
            resp_headers["x-lb-backend"] = backend.id

            # Decrement active connections
            from server.core import db
            await db.update("lb_backends", backend.id, {
                "active_connections": max(0, backend.active_connections),
            })

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
            )

        except httpx.TimeoutException:
            logger.error("Proxy timeout to %s:%d", backend.ip, backend.port)
            await self._mark_backend_error(backend)
            return JSONResponse(
                status_code=504,
                content={"error": "Backend timeout"},
            )

        except httpx.RequestError as e:
            logger.error("Proxy error to %s:%d: %s", backend.ip, backend.port, e)
            await self._mark_backend_error(backend)
            return JSONResponse(
                status_code=502,
                content={"error": "Backend unavailable"},
            )

    async def _mark_backend_error(self, backend):
        """Increment failed health checks on proxy error."""
        try:
            from server.core import db
            await db.update("lb_backends", backend.id, {
                "failed_health_checks": backend.failed_health_checks + 1,
                "active_connections": max(0, backend.active_connections - 1),
            })
        except Exception:
            pass
