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
from datetime import datetime
from io import BytesIO
from pathlib import Path

from core.models import ZarManifest
from core.workspace_config import read_config

logger = logging.getLogger("setupo.zar.packer")

EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", ".DS_Store",
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".zar"}


def _should_exclude(name: str) -> bool:
    """Check if a file/dir should be excluded from the .zar."""
    base = os.path.basename(name)
    if base in EXCLUDE_DIRS:
        return True
    if base == ".env":
        return True
    _, ext = os.path.splitext(base)
    if ext in EXCLUDE_EXTENSIONS:
        return True
    return False


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Filter for tarfile.add — skip excluded paths."""
    for part in Path(info.name).parts:
        if _should_exclude(part):
            return None
    return info


def _add_to_tar(tar: tarfile.TarFile, path: str, arcname: str):
    """Add a file/dir to tar with the filter, handling Python version differences."""
    tar.add(path, arcname=arcname, filter=_tar_filter)


def _build_tar(ws_path: Path, manifest: ZarManifest) -> bytes:
    """Build a tar.gz from workspace path and manifest. Returns bytes."""
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add manifest
        manifest_bytes = json.dumps(manifest.model_dump(), indent=2).encode()
        info = tarfile.TarInfo(name=".zar-manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, BytesIO(manifest_bytes))

        # Add config.toml if exists
        config_path = ws_path / "config.toml"
        if config_path.exists():
            tar.add(str(config_path), arcname="config.toml")

        # Add workspace files under files/
        for entry in sorted(ws_path.iterdir()):
            if _should_exclude(entry.name) or entry.name == "config.toml":
                continue
            _add_to_tar(tar, str(entry), f"files/{entry.name}")

    return buf.getvalue()


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

    config = read_config(workspace_path)
    name = config.name if config else ws_path.name
    stack = config.type if config else ""
    description = config.description if config else ""

    if not version:
        version = datetime.utcnow().strftime("%Y%m%d.%H%M%S")

    manifest = ZarManifest(
        name=name,
        version=version,
        branch=branch,
        stack=stack,
        created_at=datetime.utcnow().isoformat(),
        project_id=project_id,
        description=description,
    )

    # First pass: build tar to get content hash
    zar_bytes = _build_tar(ws_path, manifest)
    content_hash = hashlib.sha256(zar_bytes).hexdigest()

    # Second pass: rebuild with hash in manifest
    manifest.hash = f"sha256:{content_hash}"
    zar_bytes = _build_tar(ws_path, manifest)

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

        # Extract members safely
        for member in tar.getmembers():
            # Block absolute paths and traversal
            if member.name.startswith("/") or ".." in member.name:
                logger.warning("Skipping unsafe path: %s", member.name)
                continue

            if member.name == ".zar-manifest.json":
                tar.extract(member, target, filter="data")
                continue

            if member.name == "config.toml":
                tar.extract(member, target, filter="data")
                continue

            if member.name.startswith("files/"):
                member.name = member.name[6:]  # Strip files/ prefix
                if member.name:
                    resolved = (target / member.name).resolve()
                    if not str(resolved).startswith(str(target.resolve())):
                        logger.warning("Skipping path traversal: %s", member.name)
                        continue
                    tar.extract(member, target, filter="data")

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
