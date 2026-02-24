"""MMS Sandbox - Code isolation via Docker containers or venvs.
Provides the actual encapsulation of code execution.
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import docker
from docker.errors import DockerException, NotFound, APIError

from core.models import IsolationLevel, RuntimeType, ResourceSpec

logger = logging.getLogger("mms.sandbox")

CAPSULE_ROOT = Path("/var/lib/mms/capsules")
_DEV_ROOT = Path("/tmp/mms/capsules")


def _root() -> Path:
    if CAPSULE_ROOT.parent.exists():
        return CAPSULE_ROOT
    _DEV_ROOT.mkdir(parents=True, exist_ok=True)
    return _DEV_ROOT


# ── Docker Runtime Images ────────────────────────────────────────

RUNTIME_IMAGES = {
    RuntimeType.PYTHON: "python:3.12-slim",
    RuntimeType.NODE: "node:20-slim",
    RuntimeType.RUST: "rust:1.75-slim",
    RuntimeType.GO: "golang:1.22-alpine",
    RuntimeType.SHELL: "alpine:3.19",
}


class Sandbox:
    """Manages isolated execution environments for capsules."""

    def __init__(self):
        self._docker: docker.DockerClient | None = None

    @property
    def docker_client(self) -> docker.DockerClient:
        if self._docker is None:
            try:
                self._docker = docker.from_env()
                self._docker.ping()
            except DockerException:
                logger.warning("Docker not available, falling back to venv isolation")
                self._docker = None
                raise
        return self._docker

    def has_docker(self) -> bool:
        try:
            self.docker_client
            return True
        except (DockerException, Exception):
            return False

    # ── Container-based isolation ────────────────────────────────

    async def create_container(
        self,
        capsule_id: str,
        runtime: RuntimeType,
        code_path: Path,
        entrypoint: str,
        env: dict[str, str] = None,
        ports: list[int] = None,
        resources: ResourceSpec = None,
        dependencies: list[str] = None,
    ) -> dict:
        """Create a Docker container for a capsule."""
        image = RUNTIME_IMAGES.get(runtime, "python:3.12-slim")
        resources = resources or ResourceSpec()
        env = env or {}
        ports = ports or []

        # Build install command based on runtime
        install_cmd = self._build_install_cmd(runtime, dependencies or [])

        # Container config
        port_bindings = {f"{p}/tcp": None for p in ports}  # Dynamic host ports
        mem_limit = f"{resources.memory_mb}m"
        cpu_quota = int(resources.cpu * 100000)

        try:
            container = self.docker_client.containers.create(
                image=image,
                name=f"mms-{capsule_id}",
                command=self._build_run_cmd(runtime, entrypoint, install_cmd),
                environment={
                    "MMS_CAPSULE_ID": capsule_id,
                    "MMS_RUNTIME": runtime.value,
                    **env,
                },
                volumes={
                    str(code_path): {"bind": "/app", "mode": "rw"},
                },
                working_dir="/app",
                ports=port_bindings,
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                network_mode="bridge",
                detach=True,
                labels={
                    "mms.capsule_id": capsule_id,
                    "mms.runtime": runtime.value,
                },
            )

            return {
                "container_id": container.id,
                "name": container.name,
                "status": container.status,
            }

        except APIError as e:
            logger.error("Failed to create container: %s", e)
            raise

    async def start_container(self, container_id: str) -> dict:
        """Start a container and return its IP and port mappings."""
        try:
            container = self.docker_client.containers.get(container_id)
            container.start()
            container.reload()

            # Get IP from bridge network
            networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            ip = None
            for net in networks.values():
                ip = net.get("IPAddress")
                if ip:
                    break

            # Get mapped ports
            port_map = container.attrs.get("NetworkSettings", {}).get("Ports", {})

            return {
                "container_id": container_id,
                "status": container.status,
                "ip": ip,
                "ports": port_map,
            }

        except NotFound:
            raise ValueError(f"Container {container_id} not found")

    async def stop_container(self, container_id: str, timeout: int = 10):
        """Stop a running container."""
        try:
            container = self.docker_client.containers.get(container_id)
            container.stop(timeout=timeout)
        except NotFound:
            logger.warning("Container %s not found", container_id)

    async def remove_container(self, container_id: str, force: bool = True):
        """Remove a container and its volumes."""
        try:
            container = self.docker_client.containers.get(container_id)
            container.remove(force=force, v=True)
        except NotFound:
            pass

    async def exec_in_container(self, container_id: str, command: str,
                                 timeout: int = 60) -> dict:
        """Execute a command inside a running container."""
        try:
            container = self.docker_client.containers.get(container_id)
            exit_code, output = container.exec_run(
                cmd=["sh", "-c", command],
                demux=True,
            )
            stdout = output[0].decode() if output[0] else ""
            stderr = output[1].decode() if output[1] else ""

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            }

        except NotFound:
            return {"error": f"Container {container_id} not found", "exit_code": -1}
        except Exception as e:
            return {"error": str(e), "exit_code": -1}

    async def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        """Get logs from a container."""
        try:
            container = self.docker_client.containers.get(container_id)
            return container.logs(tail=tail).decode()
        except NotFound:
            return ""

    # ── Venv-based isolation (fallback) ──────────────────────────

    async def create_venv(self, capsule_id: str, code_path: Path,
                           dependencies: list[str] = None) -> dict:
        """Create a Python virtualenv for a capsule."""
        venv_path = _root() / capsule_id / ".venv"
        venv_path.parent.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "python3", "-m", "venv", str(venv_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Install dependencies
        if dependencies:
            pip = venv_path / "bin" / "pip"
            proc = await asyncio.create_subprocess_exec(
                str(pip), "install", *dependencies,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            logger.info("Installed %d packages for %s", len(dependencies), capsule_id)

        return {
            "venv_path": str(venv_path),
            "python": str(venv_path / "bin" / "python"),
        }

    async def run_in_venv(self, capsule_id: str, entrypoint: str,
                           env: dict[str, str] = None) -> dict:
        """Run code in a venv."""
        venv_path = _root() / capsule_id / ".venv"
        code_path = _root() / capsule_id
        python = str(venv_path / "bin" / "python")

        full_env = {**os.environ, "MMS_CAPSULE_ID": capsule_id}
        if env:
            full_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            python, entrypoint,
            cwd=str(code_path),
            env=full_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return {"pid": proc.pid, "python": python}

    async def exec_in_venv(self, capsule_id: str, command: str,
                            timeout: int = 60) -> dict:
        """Execute a command in a capsule's venv context."""
        venv_path = _root() / capsule_id / ".venv"
        code_path = _root() / capsule_id
        activate = f"source {venv_path}/bin/activate && {command}"

        try:
            proc = await asyncio.create_subprocess_shell(
                activate,
                cwd=str(code_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "exit_code": proc.returncode,
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "Command timed out", "exit_code": -1}

    # ── File management ──────────────────────────────────────────

    def write_capsule_code(self, capsule_id: str, filename: str, content: str) -> Path:
        """Write a code file into a capsule's workspace."""
        capsule_dir = _root() / capsule_id
        capsule_dir.mkdir(parents=True, exist_ok=True)
        filepath = capsule_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        return filepath

    def get_capsule_path(self, capsule_id: str) -> Path:
        return _root() / capsule_id

    def cleanup_capsule(self, capsule_id: str):
        """Remove all files for a capsule."""
        path = _root() / capsule_id
        if path.exists():
            shutil.rmtree(path)

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_install_cmd(runtime: RuntimeType, deps: list[str]) -> str:
        if not deps:
            return ""
        if runtime == RuntimeType.PYTHON:
            return f"pip install --no-cache-dir {' '.join(deps)}"
        elif runtime == RuntimeType.NODE:
            return f"npm install {' '.join(deps)}"
        elif runtime == RuntimeType.RUST:
            return f"cargo install {' '.join(deps)}"
        elif runtime == RuntimeType.GO:
            return " && ".join(f"go install {d}" for d in deps)
        return ""

    @staticmethod
    def _build_run_cmd(runtime: RuntimeType, entrypoint: str, install_cmd: str) -> str:
        parts = []
        if install_cmd:
            parts.append(install_cmd)

        if runtime == RuntimeType.PYTHON:
            parts.append(f"python {entrypoint}")
        elif runtime == RuntimeType.NODE:
            parts.append(f"node {entrypoint}")
        elif runtime == RuntimeType.RUST:
            parts.append(f"cargo run")
        elif runtime == RuntimeType.GO:
            parts.append(f"go run {entrypoint}")
        elif runtime == RuntimeType.SHELL:
            parts.append(f"sh {entrypoint}")
        else:
            parts.append(f"./{entrypoint}")

        return f"sh -c '{' && '.join(parts)}'"
