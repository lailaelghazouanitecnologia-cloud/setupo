"""
ServiceManager — centralized lifecycle management for background services.

Replaces the ad-hoc start/stop pattern in main.py with a proper manager
that handles ordering, health checks, restart on failure, and clean shutdown.

Usage:
    manager = ServiceManager()
    manager.register("monitor", start_fn, stop_fn, health_fn, depends_on=[])
    manager.register("reconciler", start_fn, stop_fn, depends_on=["monitor"])

    await manager.start_all()   # starts in dependency order
    await manager.stop_all()    # stops in reverse order
    manager.status()            # returns health of all services
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from nso.shared.events import emit

logger = logging.getLogger("nso.manager")

StartFn = Callable[[], Coroutine[Any, Any, None]]
StopFn = Callable[[], Coroutine[Any, Any, None]]
HealthFn = Callable[[], Coroutine[Any, Any, bool]]


class ServiceState(str, Enum):
    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ServiceEntry:
    name: str
    start_fn: StartFn
    stop_fn: StopFn
    health_fn: HealthFn | None = None
    depends_on: list[str] = field(default_factory=list)
    state: ServiceState = ServiceState.REGISTERED
    started_at: float = 0.0
    restart_count: int = 0
    last_error: str = ""
    max_restarts: int = 5

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "uptime": round(time.monotonic() - self.started_at) if self.started_at else 0,
            "restart_count": self.restart_count,
            "last_error": self.last_error,
            "depends_on": self.depends_on,
        }


class ServiceManager:
    """
    Manages background services with dependency ordering, health checks,
    and automatic restart on failure.
    """

    def __init__(self):
        self._services: dict[str, ServiceEntry] = {}
        self._health_task: asyncio.Task | None = None
        self._health_interval: int = 30  # seconds

    def register(
        self,
        name: str,
        start_fn: StartFn,
        stop_fn: StopFn,
        health_fn: HealthFn | None = None,
        depends_on: list[str] | None = None,
        max_restarts: int = 5,
    ):
        """Register a service. Must be called before start_all()."""
        if name in self._services:
            logger.warning("Service '%s' already registered, overwriting", name)
        self._services[name] = ServiceEntry(
            name=name,
            start_fn=start_fn,
            stop_fn=stop_fn,
            health_fn=health_fn,
            depends_on=depends_on or [],
            max_restarts=max_restarts,
        )
        logger.debug("Service registered: %s (depends_on=%s)", name, depends_on)

    async def start_all(self):
        """Start all services in dependency order."""
        order = self._resolve_order()
        logger.info("Starting %d services: %s", len(order), " → ".join(order))

        for name in order:
            await self._start_service(name)

        # Start health monitor
        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(self._health_loop())

        await emit("manager.started", {
            "services": order,
            "count": len(order),
        }, source="service_manager")

    async def stop_all(self):
        """Stop all services in reverse dependency order."""
        # Stop health monitor first
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        order = self._resolve_order()
        order.reverse()
        logger.info("Stopping %d services: %s", len(order), " → ".join(order))

        for name in order:
            await self._stop_service(name)

        await emit("manager.stopped", {
            "services": order,
        }, source="service_manager")

    async def restart_service(self, name: str):
        """Restart a single service."""
        if name not in self._services:
            raise ValueError(f"Unknown service: {name}")
        await self._stop_service(name)
        await self._start_service(name)

    def status(self) -> dict:
        """Get status of all services."""
        services = {}
        for name, entry in self._services.items():
            services[name] = entry.to_dict()

        running = sum(1 for e in self._services.values() if e.state == ServiceState.RUNNING)
        total = len(self._services)

        return {
            "services": services,
            "total": total,
            "running": running,
            "healthy": running == total,
        }

    def get_service(self, name: str) -> dict | None:
        """Get status of a single service."""
        entry = self._services.get(name)
        return entry.to_dict() if entry else None

    # ── Internal ──

    async def _start_service(self, name: str):
        """Start a single service."""
        entry = self._services.get(name)
        if not entry:
            return

        # Check dependencies are running
        for dep in entry.depends_on:
            dep_entry = self._services.get(dep)
            if not dep_entry or dep_entry.state != ServiceState.RUNNING:
                logger.error("Cannot start '%s': dependency '%s' is not running", name, dep)
                entry.state = ServiceState.FAILED
                entry.last_error = f"Dependency '{dep}' not running"
                return

        entry.state = ServiceState.STARTING
        try:
            await entry.start_fn()
            entry.state = ServiceState.RUNNING
            entry.started_at = time.monotonic()
            logger.info("Service '%s' started", name)
        except Exception as e:
            entry.state = ServiceState.FAILED
            entry.last_error = str(e)
            logger.error("Service '%s' failed to start: %s", name, e)
            await emit("manager.service_failed", {
                "service": name,
                "error": str(e),
            }, source="service_manager")

    async def _stop_service(self, name: str):
        """Stop a single service."""
        entry = self._services.get(name)
        if not entry or entry.state in (ServiceState.STOPPED, ServiceState.REGISTERED):
            return

        entry.state = ServiceState.STOPPING
        try:
            await asyncio.wait_for(entry.stop_fn(), timeout=30)
            entry.state = ServiceState.STOPPED
            entry.started_at = 0.0
            logger.info("Service '%s' stopped", name)
        except asyncio.TimeoutError:
            entry.state = ServiceState.STOPPED
            logger.warning("Service '%s' stop timed out, forced", name)
        except Exception as e:
            entry.state = ServiceState.STOPPED
            logger.error("Service '%s' error during stop: %s", name, e)

    async def _health_loop(self):
        """Periodically check service health and restart if needed."""
        while True:
            try:
                await asyncio.sleep(self._health_interval)
                await self._check_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check error: %s", e)

    async def _check_health(self):
        """Run health checks on all running services."""
        for name, entry in self._services.items():
            if entry.state != ServiceState.RUNNING:
                continue
            if not entry.health_fn:
                continue

            try:
                healthy = await asyncio.wait_for(entry.health_fn(), timeout=10)
                if not healthy:
                    logger.warning("Service '%s' health check failed", name)
                    entry.state = ServiceState.UNHEALTHY
                    await self._try_restart(name)
            except asyncio.TimeoutError:
                logger.warning("Service '%s' health check timed out", name)
                entry.state = ServiceState.UNHEALTHY
            except Exception as e:
                logger.warning("Service '%s' health check error: %s", name, e)
                entry.state = ServiceState.UNHEALTHY
                await self._try_restart(name)

    async def _try_restart(self, name: str):
        """Try to restart an unhealthy service."""
        entry = self._services.get(name)
        if not entry:
            return

        if entry.restart_count >= entry.max_restarts:
            entry.state = ServiceState.FAILED
            entry.last_error = f"Max restarts ({entry.max_restarts}) exceeded"
            logger.error("Service '%s' exceeded max restarts, giving up", name)
            await emit("manager.service_failed", {
                "service": name,
                "restart_count": entry.restart_count,
                "error": entry.last_error,
            }, source="service_manager")
            return

        entry.restart_count += 1
        logger.info("Restarting service '%s' (attempt %d/%d)", name, entry.restart_count, entry.max_restarts)

        await self._stop_service(name)
        await asyncio.sleep(min(2 ** entry.restart_count, 30))  # exponential backoff
        await self._start_service(name)

        await emit("manager.service_restarted", {
            "service": name,
            "restart_count": entry.restart_count,
        }, source="service_manager")

    def _resolve_order(self) -> list[str]:
        """Topological sort of services based on depends_on."""
        visited: set[str] = set()
        order: list[str] = []
        visiting: set[str] = set()  # cycle detection

        def visit(name: str):
            if name in visited:
                return
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving '{name}'")

            visiting.add(name)
            entry = self._services.get(name)
            if entry:
                for dep in entry.depends_on:
                    if dep not in self._services:
                        raise ValueError(f"Service '{name}' depends on unknown service '{dep}'")
                    visit(dep)
            visiting.discard(name)
            visited.add(name)
            order.append(name)

        for name in self._services:
            visit(name)

        return order
