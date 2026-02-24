"""Setupo Orchestrator - Main Entry Point
Manages VMs, MicroVMs, Capsules and Slaves from zarnetti.com
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from server.auth import auth_middleware
from server.orchestrator import Orchestrator
from server.routes import vms, microvms, capsules, commands, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/var/log/setupo/orchestrator.log", mode="a"),
    ]
)
logger = logging.getLogger("setupo")

orchestrator = Orchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Setupo Orchestrator starting...")
    await orchestrator.start()
    yield
    logger.info("Setupo Orchestrator shutting down...")
    await orchestrator.stop()


app = FastAPI(
    title="Setupo Orchestrator",
    description="VM & MicroVM orchestration platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://zarnetti.com", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware for /api routes
app.middleware("http")(auth_middleware)

# API routes
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(vms.router, prefix="/api/vms", tags=["vms"])
app.include_router(microvms.router, prefix="/api/microvms", tags=["microvms"])
app.include_router(capsules.router, prefix="/api/capsules", tags=["capsules"])
app.include_router(commands.router, prefix="/api/commands", tags=["commands"])

# Dashboard static files
dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard", "static")
if os.path.isdir(dashboard_dir):
    app.mount("/", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


# Make orchestrator accessible from routes
app.state.orchestrator = orchestrator
