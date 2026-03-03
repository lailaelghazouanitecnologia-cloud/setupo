"""
nso-ready: Pre-compiled system and user app images for instant boot.

Two levels:
  1. System (bucket: nso-ready) — full NSO platform pre-built
     Key: system/latest.zar, system/v{version}.zar, system/manifest.json
  2. User apps (bucket: nso) — frozen user app deploys
     Key: {project_id}/_ready/{workspace}/latest.zar, manifest.json

Workflow for system build:
  1. git pull (get latest code from GitHub)
  2. npm run build (dashboards + admin)
  3. Pack server/ + instance/ + client/*/static/ into .zar
  4. Upload to nso-ready bucket
"""

import asyncio
import hashlib
import json
import logging
import subprocess
import tarfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from server.config import settings
from server.core.zar.storage import R2Client

logger = logging.getLogger("nso.ready")

# Directories to include in system .zar
SYSTEM_INCLUDE = [
    "server",
    "instance",
    "common",
    "requirements.txt",
]

# Pre-built static assets to include
SYSTEM_STATIC = [
    "client/dashboard/static",
    "client/admin/static",
]

SYSTEM_EXCLUDE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".DS_Store", ".pytest_cache", ".mypy_cache",
}
SYSTEM_EXCLUDE_EXT = {".pyc", ".pyo"}


def _should_exclude(name: str) -> bool:
    if name in SYSTEM_EXCLUDE_DIRS:
        return True
    if name.startswith(".") and name != ".env":
        return True
    ext = Path(name).suffix
    return ext in SYSTEM_EXCLUDE_EXT


def _build_system_zar(base_dir: Path, version: str) -> tuple[bytes, dict]:
    """Pack the NSO platform into a .zar for the nso-ready bucket."""
    manifest = {
        "name": "nso-system",
        "version": version,
        "type": "system",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "components": [],
    }

    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add source code directories
        for rel in SYSTEM_INCLUDE:
            full = base_dir / rel
            if not full.exists():
                continue
            manifest["components"].append(rel)
            if full.is_file():
                tar.add(str(full), arcname=f"files/{rel}")
            else:
                for item in sorted(full.rglob("*")):
                    if any(p in SYSTEM_EXCLUDE_DIRS for p in item.parts):
                        continue
                    if _should_exclude(item.name):
                        continue
                    arc = f"files/{rel}/{item.relative_to(full)}"
                    tar.add(str(item), arcname=arc)

        # Add pre-built static assets
        for rel in SYSTEM_STATIC:
            full = base_dir / rel
            if not full.exists():
                continue
            manifest["components"].append(rel)
            for item in sorted(full.rglob("*")):
                if _should_exclude(item.name):
                    continue
                arc = f"files/{rel}/{item.relative_to(full)}"
                tar.add(str(item), arcname=arc)

        # Add instance requirements separately
        inst_req = base_dir / "instance" / "requirements.txt"
        if inst_req.exists():
            tar.add(str(inst_req), arcname="files/instance/requirements.txt")

        # Write manifest
        manifest_bytes = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo(name=".zar-manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, BytesIO(manifest_bytes))

    zar_bytes = buf.getvalue()
    manifest["hash"] = f"sha256:{hashlib.sha256(zar_bytes).hexdigest()}"
    manifest["size"] = len(zar_bytes)
    return zar_bytes, manifest


async def _run_cmd(cmd: list[str], cwd: str, label: str) -> str:
    """Run a shell command async and return stdout. Raises on failure."""
    logger.info("[build] %s: %s", label, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"{label} failed (exit {proc.returncode}): {err[:500]}")
    return stdout.decode().strip()


async def _git_pull(base: Path, branch: str = "main") -> str:
    """Pull latest code from GitHub."""
    git_dir = base / ".git"
    if not git_dir.exists():
        logger.info("[build] No .git found at %s — skipping git pull", base)
        return "skipped (no .git)"
    out = await _run_cmd(
        ["git", "pull", "origin", branch, "--ff-only"],
        cwd=str(base),
        label="git pull",
    )
    return out


async def _build_dashboards(base: Path) -> dict:
    """Build dashboard and admin Next.js apps."""
    results = {}

    for app in ("dashboard", "admin"):
        app_dir = base / "client" / app
        if not (app_dir / "package.json").exists():
            logger.warning("[build] No package.json in %s — skipping", app_dir)
            results[app] = "skipped (no package.json)"
            continue

        # npm install
        await _run_cmd(["npm", "install"], cwd=str(app_dir), label=f"{app} npm install")

        # npm run build
        await _run_cmd(["npm", "run", "build"], cwd=str(app_dir), label=f"{app} npm build")

        # Copy output to static/
        out_dir = app_dir / "out"
        static_dir = app_dir / "static"
        if out_dir.exists():
            static_dir.mkdir(parents=True, exist_ok=True)
            await _run_cmd(
                ["rsync", "-a", "--delete", f"{out_dir}/", f"{static_dir}/"],
                cwd=str(app_dir),
                label=f"{app} copy to static",
            )
            results[app] = "built"
        else:
            results[app] = "built (no out/ dir)"

    return results


async def build_and_upload_system(
    version: str | None = None,
    skip_git: bool = False,
    skip_build: bool = False,
    git_branch: str = "main",
) -> dict:
    """
    Full system build pipeline:
      1. git pull (latest code from GitHub)
      2. npm run build (dashboards)
      3. Pack into .zar
      4. Upload to nso-ready bucket

    Args:
        version: Version string (auto-generated if not set).
        skip_git: Skip git pull step.
        skip_build: Skip npm build (use existing static/).
        git_branch: Branch to pull from.
    """
    base = Path("/opt/nso")
    if not base.exists():
        # Dev fallback
        base = Path(__file__).resolve().parent.parent.parent

    if not version:
        version = datetime.now(timezone.utc).strftime("%Y%m%d.%H%M%S")

    build_log = {"version": version, "steps": {}}

    # Step 1: git pull
    if not skip_git:
        try:
            git_result = await _git_pull(base, git_branch)
            build_log["steps"]["git_pull"] = git_result
        except RuntimeError as e:
            build_log["steps"]["git_pull"] = f"failed: {e}"
            logger.warning("[build] git pull failed, continuing with local files: %s", e)
    else:
        build_log["steps"]["git_pull"] = "skipped"

    # Step 2: Build dashboards
    if not skip_build:
        try:
            dashboard_results = await _build_dashboards(base)
            build_log["steps"]["build"] = dashboard_results
        except RuntimeError as e:
            raise RuntimeError(f"Dashboard build failed: {e}")
    else:
        build_log["steps"]["build"] = "skipped"

    # Step 3: Pack
    zar_bytes, manifest = _build_system_zar(base, version)
    manifest["build_log"] = build_log
    build_log["steps"]["pack"] = f"{len(zar_bytes)} bytes"
    logger.info("Built system .zar v%s (%d bytes)", version, len(zar_bytes))

    # Step 4: Upload
    r2 = R2Client(settings.r2_ready_config())
    try:
        # Upload versioned
        ok = await r2.upload(f"system/v{version}.zar", zar_bytes)
        if not ok:
            raise RuntimeError("Failed to upload versioned system .zar")

        # Upload latest
        await r2.upload("system/latest.zar", zar_bytes)

        # Upload manifest
        await r2.upload(
            "system/manifest.json",
            json.dumps(manifest, indent=2).encode(),
            content_type="application/json",
        )
        build_log["steps"]["upload"] = "ok"
    finally:
        await r2.close()

    logger.info("Uploaded system .zar v%s to nso-ready", version)
    return manifest


async def get_system_manifest() -> dict | None:
    """Get the current system manifest from nso-ready bucket."""
    r2 = R2Client(settings.r2_ready_config())
    try:
        data = await r2.download("system/manifest.json")
        if data:
            return json.loads(data)
        return None
    finally:
        await r2.close()


async def list_system_versions() -> list[str]:
    """List all system versions in nso-ready bucket."""
    r2 = R2Client(settings.r2_ready_config())
    try:
        keys = await r2.list_keys("system/v")
        versions = []
        for k in keys:
            fname = k.rsplit("/", 1)[-1]
            if fname.startswith("v") and fname.endswith(".zar"):
                versions.append(fname[1:-4])
        return sorted(versions)
    finally:
        await r2.close()


async def system_ready_exists() -> bool:
    """Check if a pre-built system .zar exists."""
    r2 = R2Client(settings.r2_ready_config())
    try:
        return await r2.exists("system/latest.zar")
    finally:
        await r2.close()


def generate_presigned_download_url(bucket: str, key: str) -> str:
    """
    Generate a simple download URL for R2.
    For cloud-init, we pass R2 credentials directly to avoid complex
    pre-signing in bash. The cloud-init script uses a Python helper.
    """
    endpoint = settings.R2_ENDPOINT.rstrip("/")
    return f"{endpoint}/{bucket}/{key}"


# ── User-level ready (freeze app deploys) ──

async def freeze_user_app(
    project_id: str,
    workspace: str,
    version: str | None = None,
) -> dict:
    """
    Freeze a user's deployed app by copying latest.zar from nso bucket
    to the _ready prefix for instant future deploys.
    """
    r2 = R2Client(settings.r2_config())
    try:
        # Download the latest deployed .zar
        zar_bytes = await r2.download_zar(project_id, workspace, "main")
        if not zar_bytes:
            raise FileNotFoundError(f"No deployed .zar found for {workspace}")

        if not version:
            version = datetime.now(timezone.utc).strftime("%Y%m%d.%H%M%S")

        ready_key = f"{project_id}/_ready/{workspace}/v{version}.zar"
        ready_latest = f"{project_id}/_ready/{workspace}/latest.zar"
        manifest_key = f"{project_id}/_ready/{workspace}/manifest.json"

        ok = await r2.upload(ready_key, zar_bytes)
        if not ok:
            raise RuntimeError("Failed to upload frozen app .zar")

        await r2.upload(ready_latest, zar_bytes)

        manifest = {
            "name": workspace,
            "version": version,
            "type": "user-app",
            "project_id": project_id,
            "hash": f"sha256:{hashlib.sha256(zar_bytes).hexdigest()}",
            "size": len(zar_bytes),
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        await r2.upload(
            manifest_key,
            json.dumps(manifest, indent=2).encode(),
            content_type="application/json",
        )
    finally:
        await r2.close()

    logger.info("Frozen user app %s/%s v%s", project_id, workspace, version)
    return manifest


async def get_user_ready_manifest(project_id: str, workspace: str) -> dict | None:
    """Get manifest for a frozen user app."""
    r2 = R2Client(settings.r2_config())
    try:
        data = await r2.download(f"{project_id}/_ready/{workspace}/manifest.json")
        if data:
            return json.loads(data)
        return None
    finally:
        await r2.close()


async def list_user_ready_versions(project_id: str, workspace: str) -> list[str]:
    """List frozen versions for a user app."""
    r2 = R2Client(settings.r2_config())
    try:
        keys = await r2.list_keys(f"{project_id}/_ready/{workspace}/v")
        versions = []
        for k in keys:
            fname = k.rsplit("/", 1)[-1]
            if fname.startswith("v") and fname.endswith(".zar"):
                versions.append(fname[1:-4])
        return sorted(versions)
    finally:
        await r2.close()


async def user_ready_exists(project_id: str, workspace: str) -> bool:
    """Check if a frozen user app exists."""
    r2 = R2Client(settings.r2_config())
    try:
        return await r2.exists(f"{project_id}/_ready/{workspace}/latest.zar")
    finally:
        await r2.close()
