"""
HostManager — lifecycle management for pool hosts.

Manages the full lifecycle of host machines in the compute pool:
- Provisioning (via Vultr + cloud-init)
- Health monitoring
- Capacity tracking
- Draining and decommissioning
- Auto-scaling host count based on demand

The HostManager runs as a background service registered with ServiceManager.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

from nso.shared import db
from nso.shared.events import emit
from nso.engine.compute import pool

logger = logging.getLogger("nso.compute.host_manager")

CHECK_INTERVAL = 30  # seconds between health sweeps
UNHEALTHY_THRESHOLD = 3  # consecutive failures before marking unhealthy
DEAD_THRESHOLD = 300  # seconds without heartbeat before marking dead
AGENT_PORT = 8081
AGENT_TIMEOUT = 10

# Auto-scaling thresholds
SCALE_UP_CPU_PERCENT = 80  # add host when avg CPU > 80%
SCALE_UP_RAM_PERCENT = 85  # add host when avg RAM > 85%
SCALE_DOWN_CPU_PERCENT = 20  # drain host when avg CPU < 20%
MIN_HOSTS = 1  # never scale below this
SCALE_COOLDOWN = 300  # seconds between scaling decisions


class HostHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"


@dataclass
class HostState:
    host_id: str
    ip: str
    consecutive_failures: int = 0
    last_check: float = 0.0
    last_success: float = 0.0
    health: HostHealth = HostHealth.HEALTHY
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    disk_percent: float = 0.0
    vm_count: int = 0


_task: asyncio.Task | None = None
_hosts: dict[str, HostState] = {}
_last_scale_time: float = 0.0


async def start():
    """Start the host manager loop."""
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("HostManager started (interval=%ds)", CHECK_INTERVAL)


async def stop():
    """Stop the host manager loop."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("HostManager stopped")


async def is_healthy() -> bool:
    """Health check for ServiceManager."""
    return _task is not None and not _task.done()


async def _loop():
    """Main host management loop."""
    while True:
        try:
            await _sweep()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("HostManager sweep error: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL)


async def _sweep():
    """Single management sweep."""
    hosts = await pool.list_hosts()
    active_hosts = [h for h in hosts if h.get("status") in ("active", "degraded")]

    # 1. Health check all active hosts
    for host in active_hosts:
        await _check_host(host)

    # 2. Handle state transitions
    for host in active_hosts:
        await _handle_state_transitions(host)

    # 3. Evaluate auto-scaling
    await _evaluate_scaling(active_hosts)


async def _check_host(host: dict):
    """Check a single host's health via its agent."""
    host_id = host["id"]
    ip = host.get("ip", "")
    if not ip:
        return

    state = _hosts.get(host_id)
    if not state:
        state = HostState(host_id=host_id, ip=ip)
        _hosts[host_id] = state

    state.last_check = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.get(f"http://{ip}:{AGENT_PORT}/health")
            if resp.status_code == 200:
                data = resp.json()
                system = data.get("system", {})

                state.cpu_percent = system.get("cpu_percent", 0)
                state.ram_percent = system.get("mem_percent", 0)
                state.disk_percent = system.get("disk_percent", 0)
                state.consecutive_failures = 0
                state.last_success = time.monotonic()
                state.health = HostHealth.HEALTHY

                # Update metrics in DB
                await pool.update_host_metrics(
                    host_id,
                    cpu=state.cpu_percent,
                    ram=state.ram_percent,
                    disk=state.disk_percent,
                )

                # Count VMs
                try:
                    vm_resp = await client.get(
                        f"http://{ip}:{AGENT_PORT}/pool/vms",
                        headers=_host_auth(host),
                    )
                    if vm_resp.status_code == 200:
                        state.vm_count = vm_resp.json().get("total", 0)
                except Exception:
                    pass

            else:
                state.consecutive_failures += 1
                logger.warning("Host %s health check returned %d", host_id, resp.status_code)
    except Exception as e:
        state.consecutive_failures += 1
        logger.debug("Host %s unreachable: %s", host_id, e)


async def _handle_state_transitions(host: dict):
    """Handle host state transitions based on health."""
    host_id = host["id"]
    state = _hosts.get(host_id)
    if not state:
        return

    current_status = host.get("status", "active")

    # Healthy → degraded
    if state.consecutive_failures >= 2 and current_status == "active":
        state.health = HostHealth.DEGRADED
        await pool.set_host_status(host_id, "degraded")
        await emit("host.degraded", {
            "host_id": host_id,
            "ip": state.ip,
            "failures": state.consecutive_failures,
        }, source="host_manager")
        logger.warning("Host %s marked as degraded (%d failures)", host_id, state.consecutive_failures)

    # Degraded → unhealthy
    elif state.consecutive_failures >= UNHEALTHY_THRESHOLD and current_status == "degraded":
        state.health = HostHealth.UNHEALTHY
        await emit("host.unhealthy", {
            "host_id": host_id,
            "ip": state.ip,
            "failures": state.consecutive_failures,
        }, source="host_manager")
        logger.error("Host %s is unhealthy (%d failures)", host_id, state.consecutive_failures)

    # Unhealthy for too long → dead (start draining)
    elif state.health == HostHealth.UNHEALTHY:
        time_since_success = time.monotonic() - state.last_success if state.last_success else DEAD_THRESHOLD + 1
        if time_since_success > DEAD_THRESHOLD:
            state.health = HostHealth.DEAD
            await pool.set_host_status(host_id, "draining")
            await emit("host.dead", {
                "host_id": host_id,
                "ip": state.ip,
                "seconds_down": int(time_since_success),
            }, source="host_manager")
            logger.error("Host %s is dead, draining VMs", host_id)

    # Recovery: failures reset → restore to active
    elif state.consecutive_failures == 0 and current_status == "degraded":
        state.health = HostHealth.HEALTHY
        await pool.set_host_status(host_id, "active")
        await emit("host.recovered", {
            "host_id": host_id,
            "ip": state.ip,
        }, source="host_manager")
        logger.info("Host %s recovered, marked active", host_id)


async def _evaluate_scaling(active_hosts: list[dict]):
    """Evaluate if we need to scale up or down."""
    global _last_scale_time

    if not active_hosts:
        return

    # Cooldown
    if time.monotonic() - _last_scale_time < SCALE_COOLDOWN:
        return

    # Calculate averages
    avg_cpu = sum(_hosts.get(h["id"], HostState("", "")).cpu_percent for h in active_hosts) / len(active_hosts)
    avg_ram = sum(_hosts.get(h["id"], HostState("", "")).ram_percent for h in active_hosts) / len(active_hosts)

    # Scale up?
    if avg_cpu > SCALE_UP_CPU_PERCENT or avg_ram > SCALE_UP_RAM_PERCENT:
        _last_scale_time = time.monotonic()
        await emit("host.scale_up_needed", {
            "avg_cpu": round(avg_cpu, 1),
            "avg_ram": round(avg_ram, 1),
            "host_count": len(active_hosts),
            "reason": "cpu" if avg_cpu > SCALE_UP_CPU_PERCENT else "ram",
        }, source="host_manager")
        logger.warning(
            "Scale UP recommended: avg CPU=%.1f%%, avg RAM=%.1f%%, hosts=%d",
            avg_cpu, avg_ram, len(active_hosts),
        )

    # Scale down?
    elif len(active_hosts) > MIN_HOSTS and avg_cpu < SCALE_DOWN_CPU_PERCENT:
        # Find the least loaded host
        least_loaded = min(
            active_hosts,
            key=lambda h: _hosts.get(h["id"], HostState("", "")).vm_count,
        )
        least_state = _hosts.get(least_loaded["id"])
        if least_state and least_state.vm_count == 0:
            _last_scale_time = time.monotonic()
            await emit("host.scale_down_candidate", {
                "host_id": least_loaded["id"],
                "avg_cpu": round(avg_cpu, 1),
                "host_count": len(active_hosts),
            }, source="host_manager")
            logger.info(
                "Scale DOWN candidate: host %s (0 VMs, avg CPU=%.1f%%)",
                least_loaded["id"], avg_cpu,
            )


# ── Public queries ──

def get_host_health(host_id: str) -> dict | None:
    """Get detailed health info for a host."""
    state = _hosts.get(host_id)
    if not state:
        return None
    return {
        "host_id": state.host_id,
        "ip": state.ip,
        "health": state.health.value,
        "cpu_percent": state.cpu_percent,
        "ram_percent": state.ram_percent,
        "disk_percent": state.disk_percent,
        "vm_count": state.vm_count,
        "consecutive_failures": state.consecutive_failures,
        "uptime_since_check": round(time.monotonic() - state.last_check) if state.last_check else 0,
    }


def get_all_health() -> dict:
    """Get health summary of all tracked hosts."""
    hosts = {}
    for host_id, state in _hosts.items():
        hosts[host_id] = {
            "health": state.health.value,
            "cpu": state.cpu_percent,
            "ram": state.ram_percent,
            "vms": state.vm_count,
            "failures": state.consecutive_failures,
        }

    healthy = sum(1 for s in _hosts.values() if s.health == HostHealth.HEALTHY)
    total = len(_hosts)

    return {
        "hosts": hosts,
        "total": total,
        "healthy": healthy,
        "all_healthy": healthy == total,
    }


def _host_auth(host: dict) -> dict:
    """Build auth headers for host agent."""
    token = host.get("agent_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
