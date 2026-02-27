"""Setupo Server — API platform for AI agents to manage infrastructure.

FastAPI application serving the REST API and dashboard.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import db
from core.errors import SetupoError
from server.config import settings
from server.routes import auth, health, projects, instances, workspaces, domains, deploy, zar, plugins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("setupo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Setupo starting...")
    await db.init_db()
    yield
    logger.info("Setupo shutting down...")
    await db.close_db()


app = FastAPI(
    title="Setupo — AI Agent Infrastructure API",
    description=(
        "API for AI agents to manage projects, workspaces, compute instances, "
        "domains, and deployments. Supports Vultr VPS and Cloudflare DNS."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Error handler ────────────────────────────────────────────────

@app.exception_handler(SetupoError)
async def setupo_error_handler(request: Request, exc: SetupoError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


# ── Routes ───────────────────────────────────────────────────────

# Public
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(health.router, prefix="/api", tags=["health"])

# Project management (admin or API key)
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])

# Project-scoped resources (require API key)
app.include_router(
    instances.router,
    prefix="/api/projects/{project_id}/instances",
    tags=["instances"],
)
app.include_router(
    workspaces.router,
    prefix="/api/projects/{project_id}/workspaces",
    tags=["workspaces"],
)
app.include_router(
    domains.router,
    prefix="/api/projects/{project_id}/domains",
    tags=["domains"],
)
app.include_router(
    deploy.router,
    prefix="/api/projects/{project_id}/instances",
    tags=["deploy"],
)
app.include_router(
    zar.router,
    prefix="/api/projects/{project_id}/zar",
    tags=["zar"],
)
app.include_router(
    plugins.router,
    prefix="/api/projects/{project_id}/plugins",
    tags=["plugins"],
)


# ── Dashboard (static files — only for local dev) ───────────────
# In production, nginx serves the frontend from /var/www/setupo.
# Only mount here for local development when no reverse proxy is present.

if os.environ.get("SETUPO_SERVE_STATIC"):
    from fastapi.staticfiles import StaticFiles
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
    if os.path.isdir(dashboard_dir):
        app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


# ── Entrypoint ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
