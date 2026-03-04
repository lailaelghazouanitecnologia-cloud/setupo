import os
import logging
from contextlib import asynccontextmanager

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.core import db
from server.core.errors import NsoError
from server.config import settings
from server.ratelimit import RateLimitMiddleware


SERVER_MODE = settings.SERVER_MODE  # "admin", "user", "full"


class AdminHostMiddleware(BaseHTTPMiddleware):
    """
    Restrict /api/admin/* routes to requests from sonfazt.nso.dev.
    In dev mode (localhost), admin routes are always accessible.
    """

    ADMIN_HOSTS = {"sonfazt.nso.dev", "localhost", "127.0.0.1"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/admin"):
            host = request.headers.get("host", "").split(":")[0]
            if host not in self.ADMIN_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"error": "Admin panel is only accessible via sonfazt.nso.dev"},
                )
        return await call_next(request)


class ServerModeMiddleware(BaseHTTPMiddleware):
    """
    Block routes based on NSO_SERVER_MODE.
    - admin mode: block nothing (full access)
    - user mode: block /api/admin/*, orchestrator monitor only
    - full: everything enabled (default, dev)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if SERVER_MODE == "user" and path.startswith("/api/admin"):
            return JSONResponse(
                status_code=404,
                content={"error": "Not found"},
            )

        if SERVER_MODE == "admin":
            # On admin instance, optionally restrict by IP
            allowed = [ip.strip() for ip in settings.ADMIN_ALLOWED_IPS if ip.strip()]
            if allowed:
                client_ip = request.client.host if request.client else ""
                forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                real_ip = forwarded or client_ip
                if real_ip not in allowed and "127.0.0.1" != real_ip:
                    return JSONResponse(
                        status_code=403,
                        content={"error": "Access denied"},
                    )

        return await call_next(request)


# ── Imports ────────────────────────────────────────────────

from server.routes import auth, health, projects, instances, workspaces, domains, deploy, zar, plugins, billing, modules, notifications, subdomain, plugin_api, ready, secrets
from server.routes.addons import catalog as addons_catalog, connectors as addons_connectors, marketplace as addons_marketplace

# Admin-only imports (skip in user mode to avoid loading unnecessary code)
if SERVER_MODE in ("admin", "full"):
    from server.routes import admin, orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nso")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NSO starting in '%s' mode...", SERVER_MODE)
    await db.init_db()

    # Only start orchestrator monitor on admin/full instances
    stop_monitor = None
    if SERVER_MODE in ("admin", "full"):
        from server.core.orchestrator.monitor import start_monitor, stop_monitor as _stop
        await start_monitor()
        stop_monitor = _stop

    yield

    logger.info("NSO shutting down...")
    if stop_monitor:
        await stop_monitor()
    await db.close_db()


app = FastAPI(
    title="NSO — Infrastructure API",
    version="0.2.0",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────

app.add_middleware(RateLimitMiddleware)
app.add_middleware(ServerModeMiddleware)
if SERVER_MODE in ("admin", "full"):
    app.add_middleware(AdminHostMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(NsoError)
async def nso_error_handler(request: Request, exc: NsoError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


# ── Shared routes (available in all modes) ─────────────────

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(instances.router, prefix="/api/projects/{project_id}/instances", tags=["instances"])
app.include_router(workspaces.router, prefix="/api/projects/{project_id}/workspaces", tags=["workspaces"])
app.include_router(domains.router, prefix="/api/projects/{project_id}/domains", tags=["domains"])
app.include_router(deploy.router, prefix="/api/projects/{project_id}/instances", tags=["deploy"])
app.include_router(zar.router, prefix="/api/projects/{project_id}/zar", tags=["zar"])
app.include_router(plugins.router, prefix="/api/projects/{project_id}/plugins", tags=["plugins"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(modules.router, prefix="/api/modules", tags=["modules"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(subdomain.router, prefix="/api/subdomain", tags=["subdomain"])
app.include_router(plugin_api.router, prefix="/api/projects/{project_id}/p", tags=["plugin-api"])
app.include_router(addons_catalog.router, prefix="/api/projects/{project_id}/addons", tags=["addons"])
app.include_router(addons_connectors.router, prefix="/api/projects/{project_id}/addons/connectors", tags=["addons-connectors"])
app.include_router(addons_marketplace.router, prefix="/api/projects/{project_id}/addons/marketplace", tags=["addons-marketplace"])
app.include_router(secrets.router, prefix="/api/projects/{project_id}/secrets", tags=["secrets"])
app.include_router(ready.admin_router, prefix="/api/ready", tags=["ready"])
app.include_router(ready.project_router, prefix="/api/projects/{project_id}/ready", tags=["ready"])

# ── Admin-only routes ──────────────────────────────────────

if SERVER_MODE in ("admin", "full"):
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(orchestrator.router, prefix="/api/admin/orchestrator", tags=["orchestrator"])

# ── Static files ───────────────────────────────────────────

if os.environ.get("NSO_SERVE_STATIC"):
    from fastapi.staticfiles import StaticFiles
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
