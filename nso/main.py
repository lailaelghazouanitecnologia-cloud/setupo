import os
import hmac
import logging
import importlib
from pathlib import Path
from contextlib import asynccontextmanager

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nso.shared import db
from nso.shared.errors import NsoError
from nso.shared.ratelimit import RateLimitMiddleware
from nso.config import settings

SERVER_MODE = settings.SERVER_MODE

_ADMIN_SECRET_EXEMPT = {"/api/health", "/api/billing/stripe/webhook"}


class AdminHostMiddleware(BaseHTTPMiddleware):
    ADMIN_HOSTS = {"sonfazt.nso.dev", "localhost", "127.0.0.1"}

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        is_admin_host = host in self.ADMIN_HOSTS

        # Block /api/admin/* from non-admin hosts
        if request.url.path.startswith("/api/admin") and not is_admin_host:
            return JSONResponse(
                status_code=403,
                content={"error": "Admin panel is only accessible via sonfazt.nso.dev"},
            )

        # Tag request so login route knows if this is an admin-allowed host
        request.state.is_admin_host = is_admin_host
        return await call_next(request)


class ServerModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if SERVER_MODE == "user" and path.startswith("/api/admin"):
            return JSONResponse(status_code=404, content={"error": "Not found"})

        if SERVER_MODE == "admin":
            if path not in _ADMIN_SECRET_EXEMPT:
                admin_secret = settings.ADMIN_SECRET
                if admin_secret:
                    provided = request.headers.get("x-admin-secret", "")
                    if not provided or not hmac.compare_digest(provided, admin_secret):
                        return JSONResponse(status_code=403, content={"error": "Access denied"})

                allowed = [ip.strip() for ip in settings.ADMIN_ALLOWED_IPS if ip.strip()]
                if allowed:
                    client_ip = request.client.host if request.client else ""
                    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    real_ip = forwarded or client_ip
                    if real_ip not in allowed and real_ip != "127.0.0.1":
                        return JSONResponse(status_code=403, content={"error": "Access denied"})

        return await call_next(request)



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nso")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NSO starting in '%s' mode...", SERVER_MODE)
    await db.init_db()

    services = None
    if SERVER_MODE in ("admin", "full"):
        from nso.shared.manager import ServiceManager
        from nso.engine.orchestrator.monitor import start_monitor, stop_monitor
        from nso.engine.orchestrator.lb_health import start_health_checker, stop_health_checker
        from nso.engine.orchestrator.reconciler import start_reconciler, stop_reconciler
        from nso.engine.compute.pool_reconciler import start_pool_reconciler, stop_pool_reconciler
        from nso.engine.compute import host_manager, vm_manager

        # Run migrations
        from nso.engine.orchestrator.state import SPEC_MIGRATIONS
        from nso.shared.events import EVENTS_MIGRATION, set_persist_handler, _db_persist_handler
        from nso.engine.compute.pool import POOL_MIGRATIONS, seed_plans
        from nso.engine.compute.quota import QUOTA_MIGRATIONS
        conn = await db.get_db()
        for migration in SPEC_MIGRATIONS + EVENTS_MIGRATION + POOL_MIGRATIONS + QUOTA_MIGRATIONS:
            await conn.execute(migration)
        await conn.commit()

        await seed_plans()
        set_persist_handler(_db_persist_handler)

        # Register all background services with dependency ordering
        services = ServiceManager()
        services.register("monitor", start_monitor, stop_monitor)
        services.register("lb_health", start_health_checker, stop_health_checker)
        services.register("reconciler", start_reconciler, stop_reconciler,
                          depends_on=["monitor"])
        services.register("host_manager", host_manager.start, host_manager.stop,
                          health_fn=host_manager.is_healthy)
        services.register("vm_manager", vm_manager.start, vm_manager.stop,
                          health_fn=vm_manager.is_healthy,
                          depends_on=["host_manager"])
        services.register("pool_reconciler", start_pool_reconciler, stop_pool_reconciler,
                          depends_on=["host_manager"])

        await services.start_all()
        app.state.services = services

    yield

    logger.info("NSO shutting down...")
    if services:
        await services.stop_all()
    await db.close_db()


app = FastAPI(
    title="NSO — Infrastructure API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
if SERVER_MODE == "admin":
    from nso.engine.orchestrator.lb_proxy import LBProxyMiddleware
    app.add_middleware(LBProxyMiddleware)
app.add_middleware(ServerModeMiddleware)
if SERVER_MODE in ("admin", "full"):
    app.add_middleware(AdminHostMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Secret"],
)


@app.exception_handler(NsoError)
async def nso_error_handler(request: Request, exc: NsoError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


from nso.engine.auth import routes as auth_routes
from nso.engine.auth import subdomain_routes
from nso.engine.compute import health_routes
from nso.engine.projects import routes as projects_routes
from nso.engine.compute import routes as compute_routes
from nso.engine.workspace import routes as workspace_routes
from nso.engine.workspace import secrets_routes
from nso.engine.dns import routes as dns_routes
from nso.engine.deploy import routes as deploy_routes
from nso.engine.storage import routes as storage_routes
from nso.engine.addons import plugins_routes, plugin_api_routes, modules_routes
from nso.engine.addons.routes_addons import catalog as addons_catalog
from nso.engine.addons.routes_addons import connectors as addons_connectors
from nso.engine.addons.routes_addons import marketplace as addons_marketplace
from nso.engine.addons.routes_addons import webhooks as github_webhooks
from nso.engine.addons.routes_addons import ai_apps as ai_apps_routes
from nso.engine.billing import routes as billing_routes
from nso.engine.notifications import routes as notifications_routes
from nso.engine.build import routes as build_routes
from nso.engine.deploy_agent import routes as deploy_agent_routes
from nso.engine.compute import ready_routes
from nso.engine.compute import pool_routes

app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])
app.include_router(subdomain_routes.router, prefix="/api/subdomain", tags=["subdomain"])
app.include_router(health_routes.router, prefix="/api", tags=["health"])
app.include_router(projects_routes.router, prefix="/api/projects", tags=["projects"])
app.include_router(compute_routes.router, prefix="/api/projects/{project_id}/instances", tags=["instances"])
app.include_router(workspace_routes.router, prefix="/api/projects/{project_id}/workspaces", tags=["workspaces"])
app.include_router(secrets_routes.router, prefix="/api/projects/{project_id}/secrets", tags=["secrets"])
app.include_router(dns_routes.router, prefix="/api/projects/{project_id}/domains", tags=["domains"])
app.include_router(deploy_routes.router, prefix="/api/projects/{project_id}/instances", tags=["deploy"])
app.include_router(storage_routes.router, prefix="/api/projects/{project_id}/zar", tags=["zar"])
app.include_router(plugins_routes.router, prefix="/api/projects/{project_id}/plugins", tags=["plugins"])
app.include_router(billing_routes.router, prefix="/api/billing", tags=["billing"])
app.include_router(modules_routes.router, prefix="/api/modules", tags=["modules"])
app.include_router(notifications_routes.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(build_routes.router, prefix="/api/projects/{project_id}/build", tags=["build"])
app.include_router(deploy_agent_routes.router, prefix="/api/projects/{project_id}/deploy-agent", tags=["deploy-agent"])
app.include_router(plugin_api_routes.router, prefix="/api/projects/{project_id}/p", tags=["plugin-api"])
app.include_router(addons_catalog.router, prefix="/api/projects/{project_id}/addons", tags=["addons"])
app.include_router(addons_connectors.router, prefix="/api/projects/{project_id}/addons/connectors", tags=["addons-connectors"])
app.include_router(addons_marketplace.router, prefix="/api/projects/{project_id}/addons/marketplace", tags=["addons-marketplace"])
app.include_router(github_webhooks.router, prefix="/api/projects/{project_id}/webhooks/github", tags=["webhooks"])
app.include_router(ai_apps_routes.admin_router, prefix="/api/admin/ai/apps", tags=["ai-apps-admin"])
app.include_router(ai_apps_routes.project_router, prefix="/api/projects/{project_id}/ai/apps", tags=["ai-apps"])
app.include_router(ready_routes.admin_router, prefix="/api/ready", tags=["ready"])
app.include_router(ready_routes.project_router, prefix="/api/projects/{project_id}/ready", tags=["ready"])
app.include_router(pool_routes.router, prefix="/api/compute/pool", tags=["compute-pool"])

if SERVER_MODE in ("admin", "full"):
    from nso.engine.admin import routes as admin_routes
    from nso.engine.orchestrator import routes as orchestrator_routes
    from nso.engine.orchestrator import lb_routes
    app.include_router(admin_routes.router, prefix="/api/admin", tags=["admin"])
    app.include_router(orchestrator_routes.router, prefix="/api/admin/orchestrator", tags=["orchestrator"])
    app.include_router(lb_routes.router, prefix="/api/admin/lb", tags=["load-balancer"])

from nso.engine.workspace import share_routes
app.include_router(share_routes.join_router, prefix="/api", tags=["workspace-sharing"])

if os.environ.get("NSO_SERVE_STATIC"):
    from fastapi.staticfiles import StaticFiles
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "client", "dashboard", "static")
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "nso.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
