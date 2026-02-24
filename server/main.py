"""MMS Server - Micro Module System API.
Main FastAPI application serving the API and dashboard at zarnetti.com.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from core.engine import Engine
from server.routes import capsules, environments, pipelines, commands, health
from server.ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mms")

engine = Engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MMS starting...")
    await engine.start()
    yield
    logger.info("MMS shutting down...")
    await engine.stop()


app = FastAPI(
    title="MMS - Micro Module System",
    description="Encapsulated code modules, environments and pipelines",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://zarnetti.com", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store engine reference for routes
app.state.engine = engine

# API routes
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(capsules.router, prefix="/api/capsules", tags=["capsules"])
app.include_router(environments.router, prefix="/api/envs", tags=["environments"])
app.include_router(pipelines.router, prefix="/api/pipelines", tags=["pipelines"])
app.include_router(commands.router, prefix="/api/commands", tags=["commands"])
app.include_router(ws_router, prefix="/ws", tags=["websocket"])

# Dashboard
dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
if os.path.isdir(dashboard_dir):
    app.mount("/", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")
