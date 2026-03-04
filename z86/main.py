"""
z86 — Self-hosted S3-compatible object storage.

Runs as a standalone FastAPI service on port 8082.
Provides:
  - S3-compatible API (PUT/GET/DELETE/HEAD/LIST) with AWS4-HMAC-SHA256 auth
  - Admin API for bucket/key management (Bearer token auth)
  - Filesystem-backed storage with SQLite metadata
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from z86 import db
from z86.config import settings
from z86.s3 import router as s3_router
from z86.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("z86")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("z86 starting on %s:%d ...", settings.HOST, settings.PORT)
    logger.info("Data dir: %s", settings.DATA_DIR)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (settings.DATA_DIR / "buckets").mkdir(parents=True, exist_ok=True)
    await db.init_db()
    yield
    logger.info("z86 shutting down...")
    await db.close_db()


app = FastAPI(
    title="z86 — Object Storage",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT", "DELETE", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["ETag", "Content-Length", "x-amz-request-id"],
)


@app.get("/health")
async def health():
    stats = {}
    try:
        from z86.storage import engine
        stats = await engine.stats()
    except Exception:
        pass
    return {
        "service": "z86",
        "status": "ok",
        "version": "0.1.0",
        **stats,
    }


# Admin API (Bearer token auth)
app.include_router(admin_router, tags=["admin"])

# S3-compatible API (AWS4-HMAC-SHA256 auth) — must be last (catch-all routes)
app.include_router(s3_router, tags=["s3"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "z86.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
