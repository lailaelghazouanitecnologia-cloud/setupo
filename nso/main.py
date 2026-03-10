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
    def __init__(self, app):
        super().__init__(app)
        self._admin_hosts = frozenset(settings.ADMIN_HOSTS)

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        is_admin_host = host in self._admin_hosts

        # Block /api/admin/* from non-admin hosts
        if request.url.path.startswith("/api/admin") and not is_admin_host:
            return JSONResponse(
                status_code=403,
                content={"error": "Admin panel is only accessible from configured admin hosts"},
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
                else:
                    # No admin secret configured — block all non-exempt requests in admin mode
                    logger.warning("NSO_ADMIN_SECRET not set — blocking request to %s in admin mode", path)
                    return JSONResponse(status_code=403, content={"error": "Admin secret not configured"})

                allowed = settings.ADMIN_ALLOWED_IPS
                if allowed:
                    client_ip = request.client.host if request.client else ""
                    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                    real_ip = forwarded or client_ip
                    if real_ip not in allowed:
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

    # Initialize Redis (distributed state for multi-node clusters)
    from nso.shared import redis as nso_redis
    await nso_redis.init_redis()
    await nso_redis.register_node(role="gateway" if SERVER_MODE == "admin" else SERVER_MODE)
    await nso_redis.start_subscriber()

    services = None
    if SERVER_MODE in ("admin", "full"):
        from nso.shared.manager import ServiceManager
        from nso.engine.orchestrator.monitor import start_monitor, stop_monitor
        from nso.engine.orchestrator.lb_health import start_health_checker, stop_health_checker
        from nso.engine.orchestrator.reconciler import start_reconciler, stop_reconciler
        from nso.engine.compute.pool_reconciler import start_pool_reconciler, stop_pool_reconciler
        from nso.engine.compute import host_manager, vm_manager
        from nso.engine.mesh.health import start_mesh_health, stop_mesh_health

        # Run migrations
        from nso.engine.orchestrator.state import SPEC_MIGRATIONS
        from nso.shared.events import EVENTS_MIGRATION, set_persist_handler, _db_persist_handler
        from nso.engine.compute.pool import POOL_MIGRATIONS, seed_plans
        from nso.engine.compute.quota import QUOTA_MIGRATIONS
        from nso.engine.infrastructure.database.migrations import DB_MIGRATIONS
        from nso.engine.infrastructure.storage.migrations import STORAGE_MIGRATIONS
        conn = await db.get_db()
        for migration in SPEC_MIGRATIONS + EVENTS_MIGRATION + POOL_MIGRATIONS + QUOTA_MIGRATIONS + DB_MIGRATIONS + STORAGE_MIGRATIONS:
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
        services.register("mesh_health", start_mesh_health, stop_mesh_health)

        await services.start_all()
        app.state.services = services

    # Start metrics collector (runs in all modes)
    from nso.engine.compute.metrics import start_collector, stop_collector
    start_collector()

    # Start service reconciler (admin/full only — needs access to all projects)
    _compute_reconciler_stop = None
    if SERVER_MODE in ("admin", "full"):
        from nso.engine.compute.reconciler import (
            start_reconciler as start_compute_reconciler,
            stop_reconciler as stop_compute_reconciler,
        )
        start_compute_reconciler()
        _compute_reconciler_stop = stop_compute_reconciler

    yield

    stop_collector()
    if _compute_reconciler_stop:
        _compute_reconciler_stop()

    logger.info("NSO shutting down...")
    if services:
        await services.stop_all()
    await nso_redis.deregister_node()
    await nso_redis.close_redis()
    await db.close_db()


app = FastAPI(
    title="NSO — Infrastructure API",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
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


from scalar_fastapi import get_scalar_api_reference

@app.get("/api/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title="NSO API Reference",
    )


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

from nso.engine.billing import routes as billing_routes
from nso.engine.notifications import routes as notifications_routes
from nso.engine.build import routes as build_routes
from nso.engine.deploy_agent import routes as deploy_agent_routes
from nso.engine.compute import ready_routes
from nso.engine.compute import pool_routes
from nso.engine.infrastructure.database import routes as infra_db_routes
from nso.engine.infrastructure.storage import routes as infra_storage_routes
from nso.engine.validator import routes as validator_routes
from nso.engine.mesh import routes as mesh_routes
from nso.engine.services import routes as services_routes
from nso.engine.compute import node_routes

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

app.include_router(ready_routes.admin_router, prefix="/api/ready", tags=["ready"])
app.include_router(ready_routes.project_router, prefix="/api/projects/{project_id}/ready", tags=["ready"])
app.include_router(pool_routes.router, prefix="/api/compute/pool", tags=["compute-pool"])
app.include_router(infra_db_routes.router, prefix="/api/projects/{project_id}/databases", tags=["databases"])
app.include_router(infra_storage_routes.router, prefix="/api/projects/{project_id}/storage", tags=["user-storage"])
app.include_router(validator_routes.router, prefix="/api/projects/{project_id}/validate", tags=["validator"])
app.include_router(mesh_routes.router, prefix="/api/projects/{project_id}/mesh", tags=["mesh"])
app.include_router(services_routes.router, prefix="/api/projects/{project_id}/services", tags=["services"])
app.include_router(services_routes.connections_router, prefix="/api/projects/{project_id}/connections", tags=["connections"])
app.include_router(node_routes.router, prefix="/api/projects/{project_id}/nodes", tags=["compute-nodes"])

if SERVER_MODE in ("admin", "full"):
    from nso.engine.admin import routes as admin_routes
    from nso.engine.orchestrator import routes as orchestrator_routes
    from nso.engine.orchestrator import lb_routes
    app.include_router(admin_routes.router, prefix="/api/admin", tags=["admin"])
    app.include_router(orchestrator_routes.router, prefix="/api/admin/orchestrator", tags=["orchestrator"])
    app.include_router(lb_routes.router, prefix="/api/admin/lb", tags=["load-balancer"])

from nso.engine.workspace import share_routes
app.include_router(share_routes.join_router, prefix="/api", tags=["workspace-sharing"])

from nso.engine.projects import member_routes
app.include_router(member_routes.router, prefix="/api/projects/{project_id}/members", tags=["project-members"])
app.include_router(member_routes.join_router, prefix="/api", tags=["project-join"])

# ── Download / Install endpoints (public) ──

@app.get("/api/install", tags=["download"])
@app.get("/install", tags=["download"])
async def get_install_script():
    """Serve the NSO agent install script. Usage: curl -fsSL https://nso.dev/install | bash"""
    from fastapi.responses import PlainTextResponse
    script_path = Path(__file__).parent / "base" / "install.sh"
    if not script_path.exists():
        return PlainTextResponse("# install.sh not found", status_code=404)
    return PlainTextResponse(
        script_path.read_text(),
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=install.sh"},
    )


@app.get("/api/download/agent", tags=["download"])
async def download_agent():
    """Download the NSO agent as a tar.gz archive."""
    import tarfile
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    agent_dir = Path(__file__).parent.parent / "vm" / "agent"
    if not agent_dir.exists():
        return JSONResponse({"error": "Agent source not found"}, status_code=404)

    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in agent_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f) and not f.name.endswith(".pyc"):
                arcname = f"agent/{f.relative_to(agent_dir)}"
                tar.add(str(f), arcname=arcname)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=nso-agent.tar.gz"},
    )


@app.get("/api/download/cli", tags=["download"])
async def download_cli():
    """Download the NSO CLI as a tar.gz archive."""
    import tarfile
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    cli_dir = Path(__file__).parent.parent / "vm" / "cli"
    nso_entry = Path(__file__).parent.parent / "vm" / "nso"
    if not cli_dir.exists():
        return JSONResponse({"error": "CLI source not found"}, status_code=404)

    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in cli_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f) and not f.name.endswith(".pyc"):
                arcname = f"cli/{f.relative_to(cli_dir)}"
                tar.add(str(f), arcname=arcname)
        if nso_entry.exists():
            tar.add(str(nso_entry), arcname="nso")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={"Content-Disposition": "attachment; filename=nso-cli.tar.gz"},
    )


if settings.SERVE_STATIC:
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
