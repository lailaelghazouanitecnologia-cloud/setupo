"""MMS Engine - The core orchestrator that manages capsules, environments and pipelines.
Coordinates between the Store (persistence), Sandbox (isolation) and networking.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from core.models import (
    Capsule, CapsuleManifest, CapsuleState, CreateCapsuleRequest,
    Environment, RuntimeType, IsolationLevel, Pipeline, PipelineStep,
    ResourceSpec,
)
from core.store import Store
from core.sandbox import Sandbox

logger = logging.getLogger("mms.engine")


class Engine:
    """Central engine that coordinates all MMS operations."""

    def __init__(self):
        self.store = Store()
        self.sandbox = Sandbox()
        self._http: httpx.AsyncClient | None = None
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start(self):
        await self.store.connect()
        self._http = httpx.AsyncClient(timeout=30)
        logger.info("MMS Engine started (docker=%s)", self.sandbox.has_docker())

    async def stop(self):
        # Stop all running capsules
        capsules = await self.store.list_capsules(state="running")
        for cap in capsules:
            try:
                await self.stop_capsule(cap["id"])
            except Exception as e:
                logger.error("Error stopping capsule %s: %s", cap["id"], e)

        if self._http:
            await self._http.aclose()
        await self.store.close()
        logger.info("MMS Engine stopped")

    # ── Capsule Lifecycle ────────────────────────────────────────

    async def create_capsule(self, req: CreateCapsuleRequest) -> dict:
        """Create a new capsule from a request."""
        capsule_id = uuid.uuid4().hex[:10]

        manifest = CapsuleManifest(
            name=req.name,
            runtime=req.runtime,
            isolation=req.isolation,
            entrypoint=req.entrypoint,
            dependencies=req.dependencies,
            env=req.env,
            ports=req.ports,
            resources=req.resources,
        )

        capsule = Capsule(id=capsule_id, manifest=manifest)

        # Write code if provided inline
        if req.code:
            self.sandbox.write_capsule_code(capsule_id, req.entrypoint, req.code)
            await self.store.add_log(capsule_id, f"Wrote {req.entrypoint} ({len(req.code)} bytes)")

        # Clone from git if provided
        if req.git_url:
            await self._clone_repo(capsule_id, req.git_url)

        await self.store.save_capsule(capsule.model_dump(mode="json"))
        await self.store.add_log(capsule_id, f"Capsule created: {req.name} ({req.runtime.value})")
        logger.info("Created capsule %s (%s)", capsule_id, req.name)

        return capsule.model_dump(mode="json")

    async def build_capsule(self, capsule_id: str) -> dict:
        """Build/prepare a capsule (install deps, build container)."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule:
            raise ValueError(f"Capsule {capsule_id} not found")

        manifest = CapsuleManifest(**capsule["manifest"])
        await self.store.update_capsule_state(capsule_id, CapsuleState.BUILDING.value)
        await self.store.add_log(capsule_id, "Building capsule...")

        try:
            code_path = self.sandbox.get_capsule_path(capsule_id)
            isolation = manifest.isolation

            if isolation == IsolationLevel.CONTAINER and self.sandbox.has_docker():
                result = await self.sandbox.create_container(
                    capsule_id=capsule_id,
                    runtime=manifest.runtime,
                    code_path=code_path,
                    entrypoint=manifest.entrypoint,
                    env=manifest.env,
                    ports=manifest.ports,
                    resources=manifest.resources,
                    dependencies=manifest.dependencies,
                )
                await self.store.update_capsule_state(
                    capsule_id, CapsuleState.READY.value,
                    container_id=result["container_id"],
                )
                await self.store.add_log(capsule_id, f"Container built: {result['container_id'][:12]}")

            elif isolation == IsolationLevel.VENV or manifest.runtime == RuntimeType.PYTHON:
                result = await self.sandbox.create_venv(
                    capsule_id=capsule_id,
                    code_path=code_path,
                    dependencies=manifest.dependencies,
                )
                await self.store.update_capsule_state(capsule_id, CapsuleState.READY.value)
                await self.store.add_log(capsule_id, f"Venv created at {result['venv_path']}")

            else:
                await self.store.update_capsule_state(capsule_id, CapsuleState.READY.value)
                await self.store.add_log(capsule_id, "Ready (no build step needed)")

            capsule = await self.store.get_capsule(capsule_id)
            return capsule

        except Exception as e:
            await self.store.update_capsule_state(
                capsule_id, CapsuleState.ERROR.value, error=str(e)
            )
            await self.store.add_log(capsule_id, f"Build failed: {e}", level="error")
            raise

    async def start_capsule(self, capsule_id: str) -> dict:
        """Start a capsule (run its entrypoint)."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule:
            raise ValueError(f"Capsule {capsule_id} not found")

        manifest = CapsuleManifest(**capsule["manifest"])

        # Auto-build if not yet built
        if capsule["state"] == CapsuleState.CREATED.value:
            await self.build_capsule(capsule_id)
            capsule = await self.store.get_capsule(capsule_id)

        container_id = capsule.get("container_id")

        try:
            if container_id:
                result = await self.sandbox.start_container(container_id)
                await self.store.update_capsule_state(
                    capsule_id, CapsuleState.RUNNING.value,
                    ip=result.get("ip"),
                    started_at=datetime.now().isoformat(),
                )
                await self.store.add_log(capsule_id, f"Started (container, IP: {result.get('ip')})")
            else:
                # Venv-based run
                result = await self.sandbox.run_in_venv(
                    capsule_id=capsule_id,
                    entrypoint=manifest.entrypoint,
                    env=manifest.env,
                )
                self._processes[capsule_id] = result.get("pid")
                await self.store.update_capsule_state(
                    capsule_id, CapsuleState.RUNNING.value,
                    pid=result.get("pid"),
                    started_at=datetime.now().isoformat(),
                )
                await self.store.add_log(capsule_id, f"Started (venv, PID: {result.get('pid')})")

            return await self.store.get_capsule(capsule_id)

        except Exception as e:
            await self.store.update_capsule_state(
                capsule_id, CapsuleState.ERROR.value, error=str(e)
            )
            await self.store.add_log(capsule_id, f"Start failed: {e}", level="error")
            raise

    async def stop_capsule(self, capsule_id: str) -> dict:
        """Stop a running capsule."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule:
            raise ValueError(f"Capsule {capsule_id} not found")

        container_id = capsule.get("container_id")

        if container_id:
            await self.sandbox.stop_container(container_id)
        elif capsule.get("pid"):
            import os, signal
            try:
                os.kill(capsule["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass

        await self.store.update_capsule_state(capsule_id, CapsuleState.STOPPED.value)
        await self.store.add_log(capsule_id, "Stopped")
        return await self.store.get_capsule(capsule_id)

    async def destroy_capsule(self, capsule_id: str) -> dict:
        """Destroy a capsule and clean up all resources."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule:
            raise ValueError(f"Capsule {capsule_id} not found")

        # Stop if running
        if capsule["state"] == CapsuleState.RUNNING.value:
            await self.stop_capsule(capsule_id)

        # Remove container
        if capsule.get("container_id"):
            await self.sandbox.remove_container(capsule["container_id"])

        # Remove files
        self.sandbox.cleanup_capsule(capsule_id)

        # Remove from store
        await self.store.delete_capsule(capsule_id)
        logger.info("Destroyed capsule %s", capsule_id)

        return {"id": capsule_id, "status": "destroyed"}

    async def exec_in_capsule(self, capsule_id: str, command: str,
                               timeout: int = 60) -> dict:
        """Execute a command inside a running capsule."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule:
            raise ValueError(f"Capsule {capsule_id} not found")

        container_id = capsule.get("container_id")
        await self.store.add_log(capsule_id, f"exec: {command[:80]}")

        if container_id:
            return await self.sandbox.exec_in_container(container_id, command, timeout)
        else:
            return await self.sandbox.exec_in_venv(capsule_id, command, timeout)

    async def get_capsule_logs(self, capsule_id: str) -> list[dict]:
        """Get logs for a capsule."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule:
            raise ValueError(f"Capsule {capsule_id} not found")

        logs = await self.store.get_logs(capsule_id)

        # Also get container logs if available
        if capsule.get("container_id"):
            try:
                container_logs = await self.sandbox.get_container_logs(capsule["container_id"])
                if container_logs:
                    logs.append({"level": "stdout", "message": container_logs, "capsule_id": capsule_id})
            except Exception:
                pass

        return logs

    # ── Environment Management ───────────────────────────────────

    async def create_environment(self, name: str, runtime: RuntimeType,
                                  version: str = "", packages: list[str] = None) -> dict:
        """Create a reusable environment."""
        env_id = uuid.uuid4().hex[:8]
        env = Environment(
            id=env_id,
            name=name,
            runtime=runtime,
            version=version,
            packages=packages or [],
        )
        await self.store.save_environment(env.model_dump(mode="json"))
        await self.store.add_log(env_id, f"Environment created: {name}")
        return env.model_dump(mode="json")

    async def list_environments(self) -> list[dict]:
        return await self.store.list_environments()

    async def destroy_environment(self, env_id: str):
        await self.store.delete_environment(env_id)
        return {"id": env_id, "status": "destroyed"}

    # ── Pipeline Execution ───────────────────────────────────────

    async def run_pipeline(self, name: str, steps: list[PipelineStep]) -> dict:
        """Execute a pipeline of capsule operations."""
        pipeline_id = uuid.uuid4().hex[:8]
        pipeline = Pipeline(id=pipeline_id, name=name, steps=steps, state="running")
        await self.store.save_pipeline(pipeline.model_dump(mode="json"))

        results = {}
        for i, step in enumerate(steps):
            step_name = f"step_{i}_{step.capsule}"
            try:
                # Resolve capsule by name
                capsule = await self.store.get_capsule_by_name(step.capsule)
                if not capsule:
                    results[step_name] = {"error": f"Capsule '{step.capsule}' not found"}
                    continue

                # Start if not running
                if capsule["state"] != CapsuleState.RUNNING.value:
                    await self.start_capsule(capsule["id"])

                # Execute params as commands if provided
                if "command" in step.params:
                    result = await self.exec_in_capsule(capsule["id"], step.params["command"])
                    results[step_name] = result
                else:
                    results[step_name] = {"status": "started", "capsule_id": capsule["id"]}

            except Exception as e:
                results[step_name] = {"error": str(e)}

        pipeline.state = "completed"
        pipeline.results = results
        await self.store.save_pipeline(pipeline.model_dump(mode="json"))
        return pipeline.model_dump(mode="json")

    # ── Capsule Communication ────────────────────────────────────

    async def call_capsule(self, capsule_id: str, path: str = "/",
                            method: str = "GET", body: dict = None) -> dict:
        """Make an HTTP call to a capsule's exposed service."""
        capsule = await self.store.get_capsule(capsule_id)
        if not capsule or not capsule.get("ip"):
            raise ValueError(f"Capsule {capsule_id} not reachable")

        ports = capsule["manifest"].get("ports", [8080])
        port = ports[0] if ports else 8080
        url = f"http://{capsule['ip']}:{port}{path}"

        try:
            if method == "GET":
                resp = await self._http.get(url)
            else:
                resp = await self._http.request(method, url, json=body)
            return {"status_code": resp.status_code, "body": resp.text}
        except httpx.RequestError as e:
            return {"error": str(e)}

    # ── Helpers ───────────────────────────────────────────────────

    async def _clone_repo(self, capsule_id: str, git_url: str):
        """Clone a git repository into a capsule's workspace."""
        target = self.sandbox.get_capsule_path(capsule_id)
        target.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", git_url, str(target),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")
        await self.store.add_log(capsule_id, f"Cloned {git_url}")

    async def get_stats(self) -> dict:
        """Get system stats."""
        import shutil
        capsules = await self.store.list_capsules()
        disk = shutil.disk_usage("/")
        running = [c for c in capsules if c["state"] == "running"]
        return {
            "capsules_total": len(capsules),
            "capsules_running": len(running),
            "environments": len(await self.store.list_environments()),
            "pipelines": len(await self.store.list_pipelines()),
            "docker_available": self.sandbox.has_docker(),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
        }
