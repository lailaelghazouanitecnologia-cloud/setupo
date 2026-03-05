"""
ProcessSupervisor — the agent's brain.

Instead of blindly calling systemctl and forgetting, the supervisor:
1. Maintains a model of DESIRED processes (from deploy spec)
2. Tracks ACTUAL process state (PID, health, resources)
3. Runs a reconciliation loop every few seconds
4. Handles: start, stop, restart, rolling update, rollback
5. Reports rich status via /health

The supervisor owns the processes. Systemd is used as a fallback
restart mechanism, but the supervisor is the primary controller.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("nso-agent.supervisor")

SUPERVISOR_STATE_FILE = Path("/opt/nso/data/supervisor-state.json")
RECONCILE_INTERVAL = 5          # seconds between reconcile sweeps
HEALTH_CHECK_INTERVAL = 10      # seconds between health probes
MAX_RESTART_COUNT = 5           # max restarts before marking FAILED
RESTART_BACKOFF_BASE = 2        # exponential backoff base (seconds)
RESTART_WINDOW = 300            # reset restart count after this many seconds of stability
DRAIN_TIMEOUT = 30              # seconds to wait for graceful shutdown
HEALTH_CHECK_TIMEOUT = 5        # seconds per health probe


class ProcessStatus(str, Enum):
    PENDING = "pending"         # desired but not yet started
    STARTING = "starting"       # process launched, waiting for health
    RUNNING = "running"         # healthy and serving
    UNHEALTHY = "unhealthy"     # running but health checks failing
    RESTARTING = "restarting"   # being restarted
    UPDATING = "updating"       # rolling update in progress
    STOPPED = "stopped"         # intentionally stopped
    FAILED = "failed"           # exceeded max restarts
    DRAINING = "draining"       # shutting down gracefully


@dataclass
class ProcessSpec:
    """What a process SHOULD look like (desired state)."""
    name: str
    command: str
    port: int = 0
    working_dir: str = "/opt/app"
    env: dict[str, str] = field(default_factory=dict)
    health_path: str = ""                   # e.g. "/health" — empty = no HTTP check
    health_interval: int = HEALTH_CHECK_INTERVAL
    depends_on: list[str] = field(default_factory=list)
    restart_policy: str = "always"          # always | on-failure | never
    max_restarts: int = MAX_RESTART_COUNT
    drain_timeout: int = DRAIN_TIMEOUT
    version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "port": self.port,
            "working_dir": self.working_dir,
            "health_path": self.health_path,
            "depends_on": self.depends_on,
            "restart_policy": self.restart_policy,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProcessSpec:
        return cls(
            name=d.get("name", ""),
            command=d.get("command", ""),
            port=int(d.get("port", 0)),
            working_dir=d.get("working_dir", d.get("cwd", "/opt/app")),
            env=d.get("env", {}),
            health_path=d.get("health_path", d.get("health", {}).get("path", "")),
            health_interval=int(d.get("health_interval", HEALTH_CHECK_INTERVAL)),
            depends_on=d.get("depends_on", []),
            restart_policy=d.get("restart_policy", "always"),
            max_restarts=int(d.get("max_restarts", MAX_RESTART_COUNT)),
            drain_timeout=int(d.get("drain_timeout", DRAIN_TIMEOUT)),
            version=d.get("version", ""),
            metadata=d.get("metadata", {}),
        )

    @classmethod
    def from_deploy_config(cls, name: str, svc_config: dict, env: dict, working_dir: str, version: str = "") -> ProcessSpec:
        """Create from a [services.X] block in deploy.toml."""
        return cls(
            name=name,
            command=svc_config.get("command", ""),
            port=int(svc_config.get("port", 0)),
            working_dir=working_dir,
            env=env,
            health_path=svc_config.get("health_path", svc_config.get("health", "")),
            depends_on=svc_config.get("depends_on", []),
            restart_policy=svc_config.get("restart_policy", "always"),
            max_restarts=int(svc_config.get("max_restarts", MAX_RESTART_COUNT)),
            version=version,
            metadata=svc_config.get("metadata", {}),
        )


@dataclass
class ProcessState:
    """What a process ACTUALLY looks like (observed state)."""
    name: str
    status: ProcessStatus = ProcessStatus.PENDING
    pid: int = 0
    port: int = 0
    version: str = ""
    started_at: float = 0.0
    restart_count: int = 0
    last_restart_at: float = 0.0
    last_health_check: float = 0.0
    last_healthy_at: float = 0.0
    consecutive_failures: int = 0
    cpu_percent: float = 0.0
    rss_mb: float = 0.0
    error: str = ""

    @property
    def alive(self) -> bool:
        if self.pid <= 0:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    @property
    def uptime_seconds(self) -> float:
        if self.started_at <= 0:
            return 0
        return time.monotonic() - self.started_at

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "pid": self.pid,
            "port": self.port,
            "version": self.version,
            "uptime": round(self.uptime_seconds),
            "restart_count": self.restart_count,
            "consecutive_failures": self.consecutive_failures,
            "cpu_percent": self.cpu_percent,
            "rss_mb": round(self.rss_mb, 1),
            "last_healthy": self.last_healthy_at,
            "error": self.error,
        }


class ProcessSupervisor:
    """
    The core process supervisor.

    Maintains desired state (specs) and actual state (processes).
    Runs a reconcile loop that converges actual → desired.
    """

    def __init__(self):
        self.desired: dict[str, ProcessSpec] = {}
        self.actual: dict[str, ProcessState] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._reconcile_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self.spec_generation: int = 0
        self.status_generation: int = 0
        self._lock = asyncio.Lock()
        self._snapshot_version: str = ""     # version to rollback to

    # ── Lifecycle ──

    async def start(self):
        """Start the supervisor loops."""
        self._load_state()
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        self._health_task = asyncio.create_task(self._health_loop())
        logger.info("Supervisor started (desired=%d, actual=%d)", len(self.desired), len(self.actual))

    async def stop(self):
        """Stop supervisor loops. Does NOT kill managed processes."""
        for task in (self._reconcile_task, self._health_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._save_state()
        logger.info("Supervisor stopped")

    async def shutdown_all(self):
        """Gracefully stop all managed processes (for agent shutdown)."""
        async with self._lock:
            for name in list(self.actual.keys()):
                await self._stop_process(name, drain=True)
        self._save_state()

    # ── Spec management ──

    def set_desired(self, specs: list[ProcessSpec], version: str = ""):
        """Replace all desired specs. Increments spec_generation."""
        self.desired = {s.name: s for s in specs}
        self.spec_generation += 1
        if version:
            self._snapshot_version = self.actual.get(
                next(iter(self.desired), ""), ProcessState("")
            ).version or ""
        logger.info(
            "Desired state updated: gen=%d, processes=%s",
            self.spec_generation, list(self.desired.keys()),
        )
        self._save_state()

    def add_desired(self, spec: ProcessSpec):
        """Add or update a single desired process."""
        self.desired[spec.name] = spec
        self.spec_generation += 1
        self._save_state()

    def remove_desired(self, name: str):
        """Remove a process from desired state (will be stopped)."""
        self.desired.pop(name, None)
        self.spec_generation += 1
        self._save_state()

    # ── Status ──

    def is_converged(self) -> bool:
        """True if actual matches desired."""
        if set(self.desired.keys()) != set(self.actual.keys()):
            return False
        for name, spec in self.desired.items():
            state = self.actual.get(name)
            if not state:
                return False
            if state.status not in (ProcessStatus.RUNNING,):
                return False
            if spec.version and state.version != spec.version:
                return False
        return True

    def get_status(self) -> dict:
        """Full supervisor status for /health endpoint."""
        return {
            "spec_generation": self.spec_generation,
            "status_generation": self.status_generation,
            "converged": self.is_converged(),
            "processes": {
                name: state.to_dict()
                for name, state in self.actual.items()
            },
            "desired": {
                name: spec.to_dict()
                for name, spec in self.desired.items()
            },
            "orphans": [
                name for name in self.actual
                if name not in self.desired
            ],
        }

    # ── Reconciliation loop ──

    async def _reconcile_loop(self):
        """Main reconciliation loop — converges actual toward desired."""
        while True:
            try:
                await self._reconcile()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Reconcile error: %s", e, exc_info=True)
            await asyncio.sleep(RECONCILE_INTERVAL)

    async def _reconcile(self):
        """Single reconciliation sweep."""
        async with self._lock:
            changed = False

            # 1. Start processes that should exist but don't
            for name, spec in self.desired.items():
                state = self.actual.get(name)

                if not state:
                    # New process — check dependencies first
                    if self._deps_ready(spec):
                        await self._start_process(spec)
                        changed = True
                    continue

                # 2. Process exists — check if alive
                if not state.alive and state.status not in (
                    ProcessStatus.PENDING,
                    ProcessStatus.STOPPED,
                    ProcessStatus.FAILED,
                    ProcessStatus.UPDATING,
                ):
                    logger.warning("Process %s (pid=%d) died unexpectedly", name, state.pid)
                    state.status = ProcessStatus.RESTARTING
                    await self._handle_crash(name, spec, state)
                    changed = True
                    continue

                # 3. Version mismatch — needs rolling update
                if spec.version and state.version != spec.version and state.status == ProcessStatus.RUNNING:
                    logger.info("Version drift: %s current=%s desired=%s", name, state.version, spec.version)
                    await self._rolling_update(name, spec)
                    changed = True
                    continue

                # 4. Process in FAILED — check if restart window expired (reset counter)
                if state.status == ProcessStatus.FAILED:
                    if time.monotonic() - state.last_restart_at > RESTART_WINDOW:
                        logger.info("Process %s: restart window expired, retrying", name)
                        state.restart_count = 0
                        state.status = ProcessStatus.PENDING
                        await self._start_process(spec)
                        changed = True

            # 5. Stop processes that shouldn't exist (orphans)
            orphans = [n for n in self.actual if n not in self.desired]
            for name in orphans:
                logger.info("Stopping orphan process: %s", name)
                await self._stop_process(name, drain=True)
                changed = True

            if changed:
                self.status_generation += 1
                self._save_state()

    def _deps_ready(self, spec: ProcessSpec) -> bool:
        """Check if all dependencies are running."""
        for dep in spec.depends_on:
            dep_state = self.actual.get(dep)
            if not dep_state or dep_state.status != ProcessStatus.RUNNING:
                return False
        return True

    # ── Health check loop ──

    async def _health_loop(self):
        """Periodic health check for all running processes."""
        while True:
            try:
                await self._check_all_health()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Health loop error: %s", e)
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _check_all_health(self):
        """Run health checks on all running processes."""
        for name, state in list(self.actual.items()):
            if state.status not in (ProcessStatus.RUNNING, ProcessStatus.UNHEALTHY):
                continue

            spec = self.desired.get(name)
            if not spec:
                continue

            # PID check
            if not state.alive:
                continue  # reconcile loop will handle this

            # Resource sampling
            await self._sample_resources(state)

            # HTTP health check (if configured)
            if spec.health_path and spec.port:
                healthy = await self._http_health_check(spec.port, spec.health_path)
                state.last_health_check = time.monotonic()

                if healthy:
                    if state.status == ProcessStatus.UNHEALTHY:
                        logger.info("Process %s recovered", name)
                    state.status = ProcessStatus.RUNNING
                    state.last_healthy_at = time.monotonic()
                    state.consecutive_failures = 0
                else:
                    state.consecutive_failures += 1
                    if state.consecutive_failures >= 3:
                        state.status = ProcessStatus.UNHEALTHY
                        logger.warning(
                            "Process %s unhealthy (%d consecutive failures)",
                            name, state.consecutive_failures,
                        )

    async def _http_health_check(self, port: int, path: str) -> bool:
        """Probe a process's health endpoint."""
        import httpx
        url = f"http://127.0.0.1:{port}{path}"
        try:
            async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
                resp = await client.get(url)
                return resp.status_code < 500
        except Exception:
            return False

    async def _sample_resources(self, state: ProcessState):
        """Read CPU and memory usage for a process."""
        if state.pid <= 0:
            return
        try:
            stat_path = f"/proc/{state.pid}/stat"
            status_path = f"/proc/{state.pid}/status"

            if os.path.exists(status_path):
                with open(status_path) as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                state.rss_mb = int(parts[1]) / 1024  # kB → MB
                            break
        except (FileNotFoundError, PermissionError, ValueError):
            pass

    # ── Process operations ──

    async def _start_process(self, spec: ProcessSpec):
        """Start a process from spec."""
        name = spec.name
        logger.info("Starting process: %s (cmd=%s)", name, spec.command[:80])

        state = self.actual.get(name) or ProcessState(name=name)
        state.status = ProcessStatus.STARTING
        state.error = ""
        self.actual[name] = state

        env = dict(os.environ)
        env.update(spec.env)
        if spec.port:
            env["PORT"] = str(spec.port)

        try:
            proc = await asyncio.create_subprocess_shell(
                spec.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=spec.working_dir,
                env=env,
                preexec_fn=os.setsid,  # new process group for clean kills
            )

            self._processes[name] = proc
            state.pid = proc.pid
            state.port = spec.port
            state.version = spec.version
            state.started_at = time.monotonic()

            # Give it a moment to crash or start
            await asyncio.sleep(1)

            if proc.returncode is not None:
                # Died immediately
                stdout, stderr = await proc.communicate()
                state.status = ProcessStatus.FAILED
                state.error = (stderr or stdout or b"").decode(errors="replace")[:500]
                logger.error("Process %s died immediately: %s", name, state.error[:200])
                return

            # Check if health endpoint responds (if configured)
            if spec.health_path and spec.port:
                healthy = False
                for attempt in range(5):
                    await asyncio.sleep(2)
                    if proc.returncode is not None:
                        break
                    healthy = await self._http_health_check(spec.port, spec.health_path)
                    if healthy:
                        break

                if not healthy and proc.returncode is not None:
                    state.status = ProcessStatus.FAILED
                    state.error = "Process exited during startup health check"
                    return
                elif not healthy:
                    # Running but not healthy yet — mark as running, health loop will catch it
                    logger.warning("Process %s started but health check not passing yet", name)

            state.status = ProcessStatus.RUNNING
            state.last_healthy_at = time.monotonic()
            logger.info("Process %s running (pid=%d, port=%d)", name, state.pid, spec.port)

        except Exception as e:
            state.status = ProcessStatus.FAILED
            state.error = str(e)[:500]
            logger.error("Failed to start %s: %s", name, e)

    async def _stop_process(self, name: str, drain: bool = False):
        """Stop a process gracefully."""
        state = self.actual.get(name)
        if not state:
            return

        proc = self._processes.get(name)
        pid = state.pid

        if drain and state.alive:
            state.status = ProcessStatus.DRAINING
            logger.info("Draining process %s (pid=%d)", name, pid)

        # SIGTERM first
        if state.alive:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

            # Wait for graceful shutdown
            timeout = self.desired.get(name, ProcessSpec(name="")).drain_timeout if drain else 5
            deadline = time.monotonic() + timeout

            while state.alive and time.monotonic() < deadline:
                await asyncio.sleep(0.5)

            # SIGKILL if still alive
            if state.alive:
                logger.warning("Process %s didn't stop gracefully, sending SIGKILL", name)
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await asyncio.sleep(0.5)

        # Wait for the asyncio process to clean up
        if proc and proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

        state.status = ProcessStatus.STOPPED
        state.pid = 0
        self._processes.pop(name, None)

        # Remove from actual if not in desired
        if name not in self.desired:
            self.actual.pop(name, None)

        logger.info("Process %s stopped", name)

    async def _handle_crash(self, name: str, spec: ProcessSpec, state: ProcessState):
        """Handle a crashed process — restart with backoff or mark FAILED."""
        self._processes.pop(name, None)
        state.pid = 0

        if spec.restart_policy == "never":
            state.status = ProcessStatus.STOPPED
            return

        if spec.restart_policy == "on-failure" and state.status == ProcessStatus.STOPPED:
            return

        # Check restart budget
        state.restart_count += 1
        state.last_restart_at = time.monotonic()

        if state.restart_count > spec.max_restarts:
            state.status = ProcessStatus.FAILED
            state.error = f"Exceeded max restarts ({spec.max_restarts})"
            logger.error(
                "Process %s FAILED — %d restarts exhausted. Triggering rollback check.",
                name, spec.max_restarts,
            )
            # If ALL processes for this version are failing, trigger rollback
            await self._maybe_rollback(name)
            return

        # Exponential backoff
        backoff = min(RESTART_BACKOFF_BASE ** state.restart_count, 60)
        logger.info("Restarting %s in %.1fs (attempt %d/%d)", name, backoff, state.restart_count, spec.max_restarts)
        await asyncio.sleep(backoff)

        await self._start_process(spec)

    async def _rolling_update(self, name: str, new_spec: ProcessSpec):
        """Update a process to a new version without downtime."""
        state = self.actual.get(name)
        if not state:
            return

        old_version = state.version
        state.status = ProcessStatus.UPDATING
        logger.info("Rolling update: %s %s → %s", name, old_version, new_spec.version)

        if new_spec.port and new_spec.health_path:
            # Blue-green: start new on temp port, verify, switch
            temp_port = new_spec.port + 10000
            temp_spec = ProcessSpec(
                name=f"{name}__new",
                command=new_spec.command,
                port=temp_port,
                working_dir=new_spec.working_dir,
                env=new_spec.env,
                health_path=new_spec.health_path,
                version=new_spec.version,
            )

            await self._start_process(temp_spec)
            new_state = self.actual.get(f"{name}__new")

            if not new_state or new_state.status != ProcessStatus.RUNNING:
                # New version failed to start — keep old
                logger.error("Rolling update FAILED for %s: new version didn't start", name)
                await self._stop_process(f"{name}__new")
                state.status = ProcessStatus.RUNNING  # revert status
                state.error = f"Update to {new_spec.version} failed: new version didn't start"
                return

            # New version healthy — stop old, start new on correct port
            await self._stop_process(name, drain=True)
            await self._stop_process(f"{name}__new")
            await self._start_process(new_spec)

            logger.info("Rolling update complete: %s → %s", name, new_spec.version)
        else:
            # Simple restart with new spec (brief downtime)
            await self._stop_process(name, drain=True)
            await self._start_process(new_spec)

    async def _maybe_rollback(self, failed_name: str):
        """If too many processes are failing, trigger automatic rollback."""
        if not self._snapshot_version:
            return

        failed_count = sum(
            1 for s in self.actual.values()
            if s.status == ProcessStatus.FAILED
        )
        total = len(self.desired)

        # Rollback if >50% of processes are failing
        if total > 0 and failed_count / total > 0.5:
            logger.error(
                "ROLLBACK TRIGGERED: %d/%d processes failed. Rolling back to version %s",
                failed_count, total, self._snapshot_version,
            )
            # The agent's deploy module handles the actual filesystem rollback.
            # We signal it by writing a rollback request file.
            rollback_request = {
                "reason": f"{failed_count}/{total} processes failed",
                "target_version": self._snapshot_version,
                "failed_processes": [
                    n for n, s in self.actual.items()
                    if s.status == ProcessStatus.FAILED
                ],
                "requested_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                Path("/opt/nso/data/rollback-request.json").write_text(
                    json.dumps(rollback_request, indent=2)
                )
            except Exception as e:
                logger.error("Failed to write rollback request: %s", e)

    # ── State persistence ──

    def _save_state(self):
        """Persist supervisor state to disk for crash recovery."""
        state = {
            "spec_generation": self.spec_generation,
            "status_generation": self.status_generation,
            "snapshot_version": self._snapshot_version,
            "desired": {
                name: {
                    "command": spec.command,
                    "port": spec.port,
                    "working_dir": spec.working_dir,
                    "health_path": spec.health_path,
                    "depends_on": spec.depends_on,
                    "restart_policy": spec.restart_policy,
                    "max_restarts": spec.max_restarts,
                    "version": spec.version,
                    "name": spec.name,
                }
                for name, spec in self.desired.items()
            },
            "actual": {
                name: {
                    "name": s.name,
                    "pid": s.pid,
                    "port": s.port,
                    "version": s.version,
                    "restart_count": s.restart_count,
                    "status": s.status.value,
                }
                for name, s in self.actual.items()
            },
        }
        try:
            SUPERVISOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = SUPERVISOR_STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            tmp.rename(SUPERVISOR_STATE_FILE)
        except Exception as e:
            logger.warning("Failed to save supervisor state: %s", e)

    def _load_state(self):
        """Restore supervisor state after agent restart."""
        if not SUPERVISOR_STATE_FILE.exists():
            return

        try:
            data = json.loads(SUPERVISOR_STATE_FILE.read_text())
            self.spec_generation = data.get("spec_generation", 0)
            self.status_generation = data.get("status_generation", 0)
            self._snapshot_version = data.get("snapshot_version", "")

            # Restore desired specs
            for name, d in data.get("desired", {}).items():
                self.desired[name] = ProcessSpec.from_dict(d)

            # Restore actual state — but re-check PIDs
            for name, d in data.get("actual", {}).items():
                state = ProcessState(name=name)
                state.pid = d.get("pid", 0)
                state.port = d.get("port", 0)
                state.version = d.get("version", "")
                state.restart_count = d.get("restart_count", 0)

                # Verify PID is still alive
                if state.pid > 0 and state.alive:
                    state.status = ProcessStatus.RUNNING
                    state.started_at = time.monotonic()
                    logger.info("Recovered process %s (pid=%d)", name, state.pid)
                else:
                    state.status = ProcessStatus.PENDING
                    state.pid = 0
                    logger.info("Process %s was running (pid=%d) but is now dead — will restart", name, d.get("pid", 0))

                self.actual[name] = state

        except Exception as e:
            logger.warning("Failed to load supervisor state: %s", e)


# ── Module-level singleton ──

supervisor = ProcessSupervisor()
