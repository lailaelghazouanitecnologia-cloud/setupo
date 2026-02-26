"""Zar Packer — Create and extract .zar packages.

A .zar is a tar.gz with structure:
    .zar-manifest.json   — package metadata + deps + hash
    config.toml          — workspace config
    files/               — actual workspace files

Excludes: .git, node_modules, __pycache__, venv, .venv, .env, *.pyc, .zar files
"""
import hashlib
import json
import logging
import os
import tarfile
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from core.models import ZarManifest, ZarDependency
from core.workspace_config import read_config

logger = logging.getLogger("setupo.zar.packer")

EXCLUDE_PATTERNS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv",
    ".env", ".DS_Store", "*.pyc", "*.pyo", ".zar",
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}


def _should_exclude(name: str) -> bool:
    """Check if a file/dir should be excluded from the .zar."""
    base = os.path.basename(name)
    if base in EXCLUDE_PATTERNS:
        return True
    _, ext = os.path.splitext(base)
    if ext in EXCLUDE_EXTENSIONS:
        return True
    if base.endswith(".zar"):
        return True
    return False


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Filter for tarfile.add — skip excluded paths."""
    parts = Path(info.name).parts
    for part in parts:
        if _should_exclude(part):
            return None
    return info


def pack(
    workspace_path: str,
    version: str | None = None,
    branch: str = "main",
    project_id: str = "",
) -> tuple[bytes, ZarManifest]:
    """Pack a workspace directory into a .zar (tar.gz bytes).

    Returns (zar_bytes, manifest).
    """
    ws_path = Path(workspace_path)
    if not ws_path.is_dir():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    # Read config.toml for metadata
    config = read_config(workspace_path)
    name = config.name if config else ws_path.name
    stack = config.type if config else ""
    description = config.description if config else ""

    if not version:
        version = config.deploy.port if config else "0.1.0"
        # Try to get version from package config
        # Default to timestamp-based version
        version = datetime.utcnow().strftime("%Y%m%d.%H%M%S")

    # Resolve dependencies from config
    deps: list[ZarDependency] = []
    # Dependencies will be read from the extended config.toml [package.dependencies]
    # For now, parsed in the resolver

    # Build manifest (hash will be updated after packing)
    manifest = ZarManifest(
        name=name,
        version=version,
        branch=branch,
        stack=stack,
        created_at=datetime.utcnow().isoformat(),
        dependencies=deps,
        project_id=project_id,
        description=description,
    )

    # Create tar.gz in memory
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add manifest
        manifest_bytes = json.dumps(manifest.model_dump(), indent=2).encode()
        manifest_info = tarfile.TarInfo(name=".zar-manifest.json")
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, BytesIO(manifest_bytes))

        # Add config.toml if it exists
        config_path = ws_path / "config.toml"
        if config_path.exists():
            tar.add(str(config_path), arcname="config.toml")

        # Add all workspace files under files/
        for entry in sorted(ws_path.iterdir()):
            if _should_exclude(entry.name):
                continue
            if entry.name == "config.toml":
                continue  # Already added at root
            arcname = f"files/{entry.name}"
            tar.add(str(entry), arcname=arcname, filter=_tar_filter)

    zar_bytes = buf.getvalue()

    # Compute hash and update manifest
    manifest.hash = f"sha256:{hashlib.sha256(zar_bytes).hexdigest()}"

    # Re-pack with correct hash in manifest
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        manifest_bytes = json.dumps(manifest.model_dump(), indent=2).encode()
        manifest_info = tarfile.TarInfo(name=".zar-manifest.json")
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, BytesIO(manifest_bytes))

        config_path = ws_path / "config.toml"
        if config_path.exists():
            tar.add(str(config_path), arcname="config.toml")

        for entry in sorted(ws_path.iterdir()):
            if _should_exclude(entry.name):
                continue
            if entry.name == "config.toml":
                continue
            arcname = f"files/{entry.name}"
            tar.add(str(entry), arcname=arcname, filter=_tar_filter)

    zar_bytes = buf.getvalue()
    manifest.hash = f"sha256:{hashlib.sha256(zar_bytes).hexdigest()}"

    logger.info("Packed %s v%s (%s, %d bytes)", name, version, branch, len(zar_bytes))
    return zar_bytes, manifest


def extract(zar_bytes: bytes, target_dir: str) -> ZarManifest:
    """Extract a .zar package to a target directory.

    Extracts files/ contents to target_dir root.
    Returns the manifest.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    manifest = None

    with tarfile.open(fileobj=BytesIO(zar_bytes), mode="r:gz") as tar:
        # First pass: read manifest
        try:
            mf = tar.extractfile(".zar-manifest.json")
            if mf:
                manifest = ZarManifest(**json.loads(mf.read()))
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("No valid manifest in .zar: %s", e)

        # Extract all members
        for member in tar.getmembers():
            if member.name == ".zar-manifest.json":
                # Save manifest to target
                tar.extract(member, target)
                continue

            if member.name == "config.toml":
                tar.extract(member, target)
                continue

            if member.name.startswith("files/"):
                # Strip the files/ prefix
                member.name = member.name[6:]  # Remove "files/"
                if member.name:  # Skip empty (the files/ dir itself)
                    # Security: prevent path traversal
                    resolved = (target / member.name).resolve()
                    if not str(resolved).startswith(str(target.resolve())):
                        logger.warning("Skipping path traversal: %s", member.name)
                        continue
                    tar.extract(member, target)

    if not manifest:
        manifest = ZarManifest(name="unknown", version="0.0.0")

    logger.info("Extracted %s v%s to %s", manifest.name, manifest.version, target_dir)
    return manifest


def read_manifest(zar_bytes: bytes) -> ZarManifest | None:
    """Read just the manifest from a .zar without extracting."""
    try:
        with tarfile.open(fileobj=BytesIO(zar_bytes), mode="r:gz") as tar:
            mf = tar.extractfile(".zar-manifest.json")
            if mf:
                return ZarManifest(**json.loads(mf.read()))
    except Exception as e:
        logger.warning("Failed to read manifest: %s", e)
    return None
