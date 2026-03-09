"""
Build API routes — smart compilation with caching.

Routes:
  POST /{name}/build       — Trigger build for workspace (resolves strategy)
  GET  /{name}/build/cache — Check if a cached build exists
  GET  /{name}/build/logs  — List build logs for workspace
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project, require_project_admin
from nso.engine.build.service import (
    compute_source_hash,
    check_cache,
    execute_build,
)
from nso.engine.storage.zar_packer import pack
from nso.engine.workspace.config import read_config, read_package_config

logger = logging.getLogger("nso.routes.build")
router = APIRouter()


class BuildRequest(BaseModel):
    branch: str = "main"
    build_command: str = ""  # override; auto-detected if empty


class BuildCacheQuery(BaseModel):
    branch: str = "main"


@router.post("/{name}/build", summary="Build workspace")
async def build_workspace(name: str, req: BuildRequest, project_id: str = Depends(require_project_admin)):
    """Build a workspace. Smart routing decides where the build runs.

    Flow:
      1. Pack the workspace source into a .zar
      2. Compute source hash for cache lookup
      3. resolve_build_strategy() picks: cached / server / agent
      4. If server: compile on NSO infra, upload artifact to R2, cache it
      5. If agent: return marker so deploy sends build to user's VPS
      6. If cached: return existing artifact key (no rebuild)
    """
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if not ws_path:
        raise HTTPException(400, f"Workspace '{name}' has no path configured")

    # Read workspace config for build command auto-detection
    config = read_config(ws_path)
    pkg_config = read_package_config(ws_path)

    # Pack source
    try:
        zar_bytes, manifest = pack(
            workspace_path=ws_path,
            version=pkg_config.version if pkg_config else None,
            branch=req.branch,
            project_id=project_id,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace directory not found: {ws_path}")

    # Determine build command
    build_command = req.build_command
    if not build_command and config:
        # Try to read from config.toml [build] section
        build_command = ""

    # Auto-detect from stack if still empty
    stack = config.type if config else ""
    if not build_command:
        build_command = _auto_detect_build_command(ws_path, stack)

    if not build_command:
        return {
            "ok": True,
            "strategy": "none",
            "reason": "No build step detected — workspace will deploy as-is",
            "source_hash": compute_source_hash(zar_bytes),
        }

    # Resolve project secrets
    resolved_secrets: dict[str, str] = {}
    try:
        rows = await db.fetch_all("project_secrets", project_id=project_id)
        for row in rows:
            k = row.get("key", "")
            v = row.get("value", "")
            if k:
                resolved_secrets[k] = v
    except Exception:
        pass

    result = await execute_build(
        project_id=project_id,
        workspace=name,
        zar_bytes=zar_bytes,
        build_command=build_command,
        stack=stack,
        secrets=resolved_secrets,
    )

    return result


@router.get("/{name}/build/cache", summary="Get build cache")
async def check_build_cache(name: str, branch: str = "main", project_id: str = Depends(require_project)):
    """Check if a cached build exists for the current workspace source."""
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if not ws_path:
        raise HTTPException(400, f"Workspace '{name}' has no path configured")

    pkg_config = read_package_config(ws_path)
    try:
        zar_bytes, manifest = pack(
            workspace_path=ws_path,
            version=pkg_config.version if pkg_config else None,
            branch=branch,
            project_id=project_id,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace directory not found: {ws_path}")

    source_hash = compute_source_hash(zar_bytes)
    cached = await check_cache(project_id, name, source_hash)

    if cached:
        return {
            "cached": True,
            "source_hash": source_hash,
            "artifact_r2_key": cached["artifact_r2_key"],
            "artifact_size": cached.get("artifact_size", 0),
            "built_on": cached.get("built_on", ""),
            "created_at": cached.get("created_at", ""),
        }

    return {
        "cached": False,
        "source_hash": source_hash,
    }


@router.get("/{name}/build/logs", summary="Get build logs")
async def list_build_logs(name: str, project_id: str = Depends(require_project)):
    """List recent build logs for a workspace."""
    logs = await db.fetch_all("build_logs", project_id=project_id, workspace=name)
    return {"workspace": name, "logs": logs[:50]}


def _auto_detect_build_command(ws_path: str, stack: str) -> str:
    """Auto-detect build command based on stack and file presence."""
    import os

    # Check for common build files
    checks = [
        ("package.json", "npm run build"),
        ("yarn.lock", "yarn build"),
        ("pnpm-lock.yaml", "pnpm build"),
        ("Makefile", "make build"),
        ("Cargo.toml", "cargo build --release"),
        ("go.mod", "go build -o app ./..."),
        ("build.gradle", "./gradlew build"),
        ("pom.xml", "mvn package -DskipTests"),
    ]

    for filename, command in checks:
        if os.path.exists(os.path.join(ws_path, filename)):
            # For package.json, verify "build" script exists
            if filename == "package.json":
                try:
                    import json
                    with open(os.path.join(ws_path, filename)) as f:
                        pkg = json.load(f)
                    if "build" not in pkg.get("scripts", {}):
                        continue
                except Exception:
                    continue
            return command

    return ""
