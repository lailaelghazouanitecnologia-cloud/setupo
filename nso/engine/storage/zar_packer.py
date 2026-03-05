import hashlib
import json
import logging
import os
import tarfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from nso.shared.models import ZarManifest
from nso.engine.workspace.config import read_config

logger = logging.getLogger("nso.zar.packer")

EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", ".DS_Store",
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".zar"}

MAX_RESOLVE_DEPTH = 5


def _should_exclude(name: str) -> bool:
    base = os.path.basename(name)
    if base in EXCLUDE_DIRS or base == ".env":
        return True
    _, ext = os.path.splitext(base)
    return ext in EXCLUDE_EXTENSIONS


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    for part in Path(info.name).parts:
        if _should_exclude(part):
            return None
    return info


def _add_to_tar(tar: tarfile.TarFile, path: str, arcname: str):
    tar.add(path, arcname=arcname, filter=_tar_filter)


def _build_tar(ws_path: Path, manifest: ZarManifest) -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        manifest_bytes = json.dumps(manifest.model_dump(), indent=2).encode()
        info = tarfile.TarInfo(name=".zar-manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, BytesIO(manifest_bytes))

        config_path = ws_path / "config.toml"
        if config_path.exists():
            tar.add(str(config_path), arcname="config.toml")

        deploy_toml_path = ws_path / "deploy.toml"
        if deploy_toml_path.exists():
            tar.add(str(deploy_toml_path), arcname="deploy.toml")

        top_level_files = {"config.toml", "deploy.toml"}
        for entry in sorted(ws_path.iterdir()):
            if _should_exclude(entry.name) or entry.name in top_level_files:
                continue
            _add_to_tar(tar, str(entry), f"files/{entry.name}")

    return buf.getvalue()


def pack(
    workspace_path: str,
    version: str | None = None,
    branch: str = "main",
    project_id: str = "",
) -> tuple[bytes, ZarManifest]:
    ws_path = Path(workspace_path)
    if not ws_path.is_dir():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    config = read_config(workspace_path)
    name = config.name if config else ws_path.name
    stack = config.type if config else ""
    description = config.description if config else ""

    if not version:
        version = datetime.now(timezone.utc).strftime("%Y%m%d.%H%M%S")

    manifest = ZarManifest(
        name=name,
        version=version,
        branch=branch,
        stack=stack,
        created_at=datetime.now(timezone.utc).isoformat(),
        project_id=project_id,
        description=description,
    )

    zar_bytes = _build_tar(ws_path, manifest)
    content_hash = hashlib.sha256(zar_bytes).hexdigest()

    manifest.hash = f"sha256:{content_hash}"
    zar_bytes = _build_tar(ws_path, manifest)

    logger.info("Packed %s v%s (%s, %d bytes)", name, version, branch, len(zar_bytes))
    return zar_bytes, manifest


def extract(zar_bytes: bytes, target_dir: str) -> ZarManifest:
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    manifest = None

    with tarfile.open(fileobj=BytesIO(zar_bytes), mode="r:gz") as tar:
        try:
            mf = tar.extractfile(".zar-manifest.json")
            if mf:
                manifest = ZarManifest(**json.loads(mf.read()))
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning("No valid manifest in .zar: %s", e)

        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                logger.warning("Skipping unsafe path: %s", member.name)
                continue

            if member.name in (".zar-manifest.json", "config.toml", "deploy.toml"):
                tar.extract(member, target)
                continue

            if not member.name.startswith("files/"):
                continue

            member.name = member.name[6:]
            if not member.name:
                continue

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
    try:
        with tarfile.open(fileobj=BytesIO(zar_bytes), mode="r:gz") as tar:
            mf = tar.extractfile(".zar-manifest.json")
            if mf:
                return ZarManifest(**json.loads(mf.read()))
    except Exception as e:
        logger.warning("Failed to read manifest: %s", e)
    return None
