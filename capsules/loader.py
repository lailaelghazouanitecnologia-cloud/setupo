"""Capsule Loader - Discovers, validates and manages capsule plugins.

A capsule is a directory with:
  capsule.yaml  - manifest (name, version, description, dependencies)
  install.sh    - installation script (runs inside target VM)
  run.sh        - start script
  stop.sh       - stop script (optional)
"""
import os
import logging
from pathlib import Path
from dataclasses import dataclass

import yaml

logger = logging.getLogger("setupo.capsules")

CAPSULE_DIRS = [
    Path("/var/lib/setupo/capsules"),
    Path(__file__).parent / "builtin",
]


@dataclass
class Capsule:
    name: str
    version: str
    description: str
    path: Path
    dependencies: list[str]
    ports: list[int]
    type: str  # "service", "task", "tool"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "path": str(self.path),
            "dependencies": self.dependencies,
            "ports": self.ports,
            "type": self.type,
        }


class CapsuleLoader:
    def __init__(self):
        self.capsules: dict[str, Capsule] = {}
        self.scan()

    def scan(self):
        """Scan all capsule directories for available capsules."""
        self.capsules.clear()
        for base_dir in CAPSULE_DIRS:
            if not base_dir.exists():
                continue
            for entry in base_dir.iterdir():
                manifest = entry / "capsule.yaml"
                if entry.is_dir() and manifest.exists():
                    try:
                        capsule = self._load_manifest(entry, manifest)
                        self.capsules[capsule.name] = capsule
                        logger.info("Found capsule: %s v%s", capsule.name, capsule.version)
                    except Exception as e:
                        logger.warning("Failed to load capsule %s: %s", entry.name, e)

    def _load_manifest(self, path: Path, manifest: Path) -> Capsule:
        data = yaml.safe_load(manifest.read_text())
        return Capsule(
            name=data["name"],
            version=data.get("version", "0.0.1"),
            description=data.get("description", ""),
            path=path,
            dependencies=data.get("dependencies", []),
            ports=data.get("ports", []),
            type=data.get("type", "service"),
        )

    def get(self, name: str) -> Capsule | None:
        return self.capsules.get(name)

    def list_capsules(self) -> list[dict]:
        return [c.to_dict() for c in self.capsules.values()]

    def get_install_script(self, name: str) -> str | None:
        capsule = self.get(name)
        if not capsule:
            return None
        script = capsule.path / "install.sh"
        if script.exists():
            return script.read_text()
        return None
