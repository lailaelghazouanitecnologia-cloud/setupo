"""
NSO Build Service — Smart remote compilation with caching.

Routing logic:
  1. Check build cache (source_hash) → if hit, return cached artifact
  2. Estimate build weight → lightweight builds run on user's own agent
  3. Heavy builds go to NSO build server (rate limited: 1/min per project)
  4. If rate exceeded → fallback to user's own agent
  5. Artifacts are stored in R2 and reused across deploys
"""

import hashlib
import logging
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

from nso.shared import db
from nso.config import settings
from nso.engine.storage.service import R2Client

logger = logging.getLogger("nso.build")

# ── Rate limiting: 1 build per minute per project on the build server ──
BUILD_RATE_WINDOW = 60  # seconds

# ── Lightweight threshold: source < 2MB → build on user's agent ──
LIGHTWEIGHT_THRESHOLD_BYTES = 2 * 1024 * 1024

# ── Build server config ──
BUILD_SERVER_URL = os.environ.get("NSO_BUILD_SERVER_URL", "")
BUILD_SERVER_TOKEN = os.environ.get("NSO_BUILD_SERVER_TOKEN", "")
BUILD_TIMEOUT = 600.0  # 10 min max

# ── R2 prefix for build artifacts ──
BUILD_ARTIFACT_PREFIX = "_builds"

# Force IPv4
_ipv4_transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")


def _build_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_ipv4_transport)


def compute_source_hash(zar_bytes: bytes) -> str:
    """SHA256 of the packed source — same source = same hash = cache hit."""
    return hashlib.sha256(zar_bytes).hexdigest()


async def _is_rate_limited(project_id: str) -> bool:
    """Check if this project has exceeded 1 build/min on the build server."""
    from nso.shared.redis import check_rate_limit
    allowed = await check_rate_limit(f"build:{project_id}", 1, BUILD_RATE_WINDOW)
    return not allowed


async def _record_build_use(project_id: str):
    """Record that this project used the build server (no-op, rate check handles it)."""
    pass


def estimate_build_weight(zar_bytes: bytes, build_command: str) -> str:
    """Classify build as 'light' or 'heavy'.

    Light builds run on the user's own agent.
    Heavy builds get routed to the NSO build server.

    Heuristics:
      - Source size < 2MB → light
      - No build command → light (nothing to build)
      - Simple commands (cp, mv, echo) → light
      - Compiled languages (cargo, go build) → heavy regardless of size
      - Python build → light (fast wheel/sdist creation)
    """
    if not build_command:
        return "light"

    # Compiled languages are always heavy (even small source = large compile)
    heavy_commands = {"cargo", "go"}
    first_word = build_command.strip().split()[0] if build_command.strip() else ""
    if first_word in heavy_commands:
        return "heavy"

    if len(zar_bytes) < LIGHTWEIGHT_THRESHOLD_BYTES:
        return "light"

    # Commands that are inherently lightweight
    light_commands = {"cp", "mv", "echo", "mkdir", "touch", "cat", "ln", "python"}
    if first_word in light_commands:
        return "light"

    return "heavy"


async def check_cache(project_id: str, workspace: str, source_hash: str) -> dict | None:
    """Look up a cached build artifact by source hash.

    Returns the cache row if found (includes artifact_r2_key), else None.
    """
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM build_cache WHERE project_id = ? AND workspace = ? AND source_hash = ?",
        (project_id, workspace, source_hash),
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


async def store_cache(
    project_id: str,
    workspace: str,
    source_hash: str,
    artifact_r2_key: str,
    artifact_size: int,
    build_command: str,
    stack: str,
    built_on: str,
    duration_s: float,
):
    """Store a build result in the cache."""
    cache_id = f"bld_{uuid.uuid4().hex[:16]}"
    await db.insert("build_cache", {
        "id": cache_id,
        "project_id": project_id,
        "workspace": workspace,
        "source_hash": source_hash,
        "artifact_r2_key": artifact_r2_key,
        "artifact_size": artifact_size,
        "build_command": build_command,
        "stack": stack,
        "built_on": built_on,
        "duration_s": duration_s,
    })
    return cache_id


async def store_build_log(
    project_id: str,
    workspace: str,
    source_hash: str,
    status: str,
    built_on: str,
    output: str,
    duration_s: float,
):
    """Record a build attempt in the log."""
    log_id = f"blog_{uuid.uuid4().hex[:16]}"
    await db.insert("build_logs", {
        "id": log_id,
        "project_id": project_id,
        "workspace": workspace,
        "source_hash": source_hash,
        "status": status,
        "built_on": built_on,
        "output": output[:5000],
        "duration_s": duration_s,
    })
    return log_id


async def upload_artifact(r2: R2Client, project_id: str, workspace: str,
                          source_hash: str, artifact_bytes: bytes) -> str:
    """Upload compiled artifact to R2 and return the key."""
    r2_key = f"{BUILD_ARTIFACT_PREFIX}/{project_id}/{workspace}/{source_hash}.tar.gz"
    await r2.upload(r2_key, artifact_bytes, content_type="application/gzip")
    return r2_key


async def download_artifact(r2: R2Client, r2_key: str) -> bytes | None:
    """Download a cached artifact from R2."""
    return await r2.download(r2_key)


async def build_on_server(
    zar_bytes: bytes,
    build_command: str,
    stack: str,
    project_id: str,
    workspace: str,
    source_hash: str,
    secrets: dict[str, str] | None = None,
) -> dict:
    """Send source to the NSO build server for compilation.

    The build server:
      1. Receives the .zar source
      2. Extracts it
      3. Runs the build command
      4. Returns the compiled artifact as tar.gz

    Returns:
        {"ok": bool, "artifact": bytes|None, "output": str, "duration_s": float}
    """
    if not BUILD_SERVER_URL:
        return {"ok": False, "artifact": None, "output": "Build server not configured", "duration_s": 0}

    try:
        async with _build_client(BUILD_TIMEOUT) as client:
            resp = await client.post(
                f"{BUILD_SERVER_URL}/build",
                headers={
                    "Authorization": f"Bearer {BUILD_SERVER_TOKEN}",
                    "X-Project-Id": project_id,
                    "X-Workspace": workspace,
                    "X-Source-Hash": source_hash,
                    "X-Build-Command": build_command,
                    "X-Stack": stack,
                },
                content=zar_bytes,
                timeout=BUILD_TIMEOUT,
            )
    except httpx.ConnectError:
        return {"ok": False, "artifact": None, "output": "Cannot connect to build server", "duration_s": 0}
    except httpx.TimeoutException:
        return {"ok": False, "artifact": None, "output": "Build timed out", "duration_s": 0}
    except httpx.HTTPError as exc:
        return {"ok": False, "artifact": None, "output": f"Build server error: {exc}", "duration_s": 0}

    if resp.status_code != 200:
        try:
            body = resp.json()
            output = body.get("output", body.get("error", resp.text[:1000]))
            duration = body.get("duration_s", 0)
        except Exception:
            output = resp.text[:1000]
            duration = 0
        return {"ok": False, "artifact": None, "output": output, "duration_s": duration}

    # Success: response body is the compiled artifact
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        # JSON response with artifact URL (alternative mode)
        body = resp.json()
        return {
            "ok": body.get("ok", True),
            "artifact": None,
            "artifact_r2_key": body.get("artifact_r2_key", ""),
            "output": body.get("output", ""),
            "duration_s": body.get("duration_s", 0),
        }
    else:
        # Binary response: the artifact itself
        duration = float(resp.headers.get("X-Build-Duration", "0"))
        return {
            "ok": True,
            "artifact": resp.content,
            "output": resp.headers.get("X-Build-Output", "Build completed"),
            "duration_s": duration,
        }


async def resolve_build_strategy(
    project_id: str,
    workspace: str,
    zar_bytes: bytes,
    build_command: str,
    stack: str,
) -> dict:
    """Decide where and how to build.

    Returns:
        {
            "strategy": "cached" | "server" | "agent",
            "reason": str,
            "cache_hit": dict | None,      # populated if cached
        }
    """
    source_hash = compute_source_hash(zar_bytes)

    # 1. Cache check — no rebuild needed
    cached = await check_cache(project_id, workspace, source_hash)
    if cached:
        logger.info("Build cache HIT for %s/%s (hash=%s)", project_id, workspace, source_hash[:12])
        return {
            "strategy": "cached",
            "reason": "Artifact already built for this exact source",
            "source_hash": source_hash,
            "cache_hit": cached,
        }

    # 2. Weight check — light builds go to user's agent
    weight = estimate_build_weight(zar_bytes, build_command)
    if weight == "light":
        logger.info("Build routed to AGENT for %s/%s (lightweight)", project_id, workspace)
        return {
            "strategy": "agent",
            "reason": f"Lightweight build ({len(zar_bytes)} bytes, command: {build_command[:50]})",
            "source_hash": source_hash,
            "cache_hit": None,
        }

    # 3. Rate limit check — heavy builds go to server if allowed
    if not BUILD_SERVER_URL:
        logger.info("Build routed to AGENT for %s/%s (no build server)", project_id, workspace)
        return {
            "strategy": "agent",
            "reason": "No build server configured",
            "source_hash": source_hash,
            "cache_hit": None,
        }

    if await _is_rate_limited(project_id):
        logger.info("Build routed to AGENT for %s/%s (rate limited)", project_id, workspace)
        return {
            "strategy": "agent",
            "reason": "Build server rate limit exceeded (1/min) — using own infrastructure",
            "source_hash": source_hash,
            "cache_hit": None,
        }

    # 4. Heavy build → NSO build server
    logger.info("Build routed to SERVER for %s/%s (heavy, %d bytes)", project_id, workspace, len(zar_bytes))
    return {
        "strategy": "server",
        "reason": f"Heavy build ({len(zar_bytes)} bytes) routed to NSO build server",
        "source_hash": source_hash,
        "cache_hit": None,
    }


async def execute_build(
    project_id: str,
    workspace: str,
    zar_bytes: bytes,
    build_command: str,
    stack: str,
    secrets: dict[str, str] | None = None,
) -> dict:
    """Full build orchestration: resolve strategy → execute → cache → return.

    Returns:
        {
            "ok": bool,
            "strategy": str,
            "source_hash": str,
            "artifact_r2_key": str,    # R2 key of compiled artifact
            "cached": bool,
            "built_on": str,
            "output": str,
            "duration_s": float,
        }
    """
    strategy = await resolve_build_strategy(
        project_id, workspace, zar_bytes, build_command, stack,
    )

    source_hash = strategy["source_hash"]

    # ── Cache hit: return immediately ──
    if strategy["strategy"] == "cached":
        hit = strategy["cache_hit"]
        return {
            "ok": True,
            "strategy": "cached",
            "source_hash": source_hash,
            "artifact_r2_key": hit["artifact_r2_key"],
            "cached": True,
            "built_on": hit.get("built_on", "server"),
            "output": "Cache hit — no rebuild needed",
            "duration_s": 0,
        }

    # ── Agent build: return marker so caller sends build to agent ──
    if strategy["strategy"] == "agent":
        return {
            "ok": True,
            "strategy": "agent",
            "source_hash": source_hash,
            "artifact_r2_key": "",
            "cached": False,
            "built_on": "agent",
            "output": strategy["reason"],
            "duration_s": 0,
        }

    # ── Server build: compile on NSO infra ──
    await _record_build_use(project_id)

    t0 = time.monotonic()
    result = await build_on_server(
        zar_bytes, build_command, stack,
        project_id, workspace, source_hash,
        secrets=secrets,
    )
    duration = time.monotonic() - t0

    if not result["ok"]:
        await store_build_log(
            project_id, workspace, source_hash,
            "failed", "server", result["output"], duration,
        )
        # Fallback to agent on server failure
        return {
            "ok": True,
            "strategy": "agent",
            "source_hash": source_hash,
            "artifact_r2_key": "",
            "cached": False,
            "built_on": "agent",
            "output": f"Build server failed ({result['output'][:200]}), falling back to agent",
            "duration_s": 0,
        }

    # Upload artifact to R2 and cache it
    artifact_r2_key = result.get("artifact_r2_key", "")
    if not artifact_r2_key and result.get("artifact"):
        r2 = R2Client(settings.r2_config())
        try:
            artifact_r2_key = await upload_artifact(
                r2, project_id, workspace, source_hash, result["artifact"],
            )
        finally:
            await r2.close()

    if artifact_r2_key:
        artifact_size = len(result.get("artifact", b"")) or 0
        await store_cache(
            project_id, workspace, source_hash,
            artifact_r2_key, artifact_size,
            build_command, stack, "server", duration,
        )

    await store_build_log(
        project_id, workspace, source_hash,
        "success", "server", result["output"][:2000], duration,
    )

    return {
        "ok": True,
        "strategy": "server",
        "source_hash": source_hash,
        "artifact_r2_key": artifact_r2_key,
        "cached": False,
        "built_on": "server",
        "output": result["output"],
        "duration_s": duration,
    }
