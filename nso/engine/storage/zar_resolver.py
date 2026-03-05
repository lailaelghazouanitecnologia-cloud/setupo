import json
import logging
import os
from pathlib import Path

from nso.shared.models import ZarDependency, ZarManifest, R2Config
from nso.engine.storage.zar_packer import extract, read_manifest
from nso.engine.storage.service import R2Client

logger = logging.getLogger("nso.zar.resolver")

MAX_DEPTH = 5


async def resolve_dependencies(
    manifest: ZarManifest,
    target_dir: str,
    r2: R2Client,
    project_id: str,
    depth: int = 0,
) -> list[str]:
    if depth > MAX_DEPTH:
        logger.error("Max dependency depth (%d) exceeded", MAX_DEPTH)
        return []

    if not manifest.dependencies:
        return []

    resolved = []
    for dep in manifest.dependencies:
        dep_path = dep.path or f"deps/{dep.name}"
        full_path = os.path.join(target_dir, dep_path)

        logger.info(
            "Resolving dep: %s@%s → %s (depth=%d)",
            dep.name, dep.branch, dep_path, depth,
        )

        zar_bytes = await r2.download_zar(
            project_id=project_id,
            workspace=dep.name,
            branch=dep.branch,
            version=dep.version if dep.version and not dep.version.startswith(">") else None,
        )

        if not zar_bytes:
            logger.warning("Dependency %s not found in R2, skipping", dep.name)
            continue

        dep_manifest = extract(zar_bytes, full_path)
        resolved.append(dep.name)

        if dep_manifest and dep_manifest.dependencies:
            sub_resolved = await resolve_dependencies(
                dep_manifest, full_path, r2, project_id, depth + 1,
            )
            resolved.extend(sub_resolved)

    return resolved


def parse_dependencies_from_toml(toml_data: dict) -> list[ZarDependency]:
    package = toml_data.get("package", {})
    deps_raw = package.get("dependencies", {})

    deps = []
    for name, config in deps_raw.items():
        if isinstance(config, dict):
            deps.append(ZarDependency(
                name=name,
                branch=config.get("branch", "main"),
                version=config.get("version", ""),
                path=config.get("path", f"deps/{name}"),
            ))
        elif isinstance(config, str):
            deps.append(ZarDependency(name=name, branch=config))

    return deps
