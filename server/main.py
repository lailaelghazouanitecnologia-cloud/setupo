import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import db
from core.errors import SetupoError
from server.config import settings
from server.routes import auth, health, projects, instances, workspaces, domains, deploy, zar, plugins, billing, modules, notifications, subdomain

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
    title="NSO — Infrastructure API",
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


@app.exception_handler(SetupoError)
async def setupo_error_handler(request: Request, exc: SetupoError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


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


if os.environ.get("SETUPO_SERVE_STATIC"):
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
