"""
Health checker — background task that polls backend health endpoints.
"""
import asyncio
import logging
from datetime import datetime

import httpx

from server.core import db
from server.core.loadbalancer.models import BackendStatus

logger = logging.getLogger("nso.lb.health")

_health_task: asyncio.Task | None = None


async def start_health_checker():
    """Start the background health check loop."""
    global _health_task
    if _health_task and not _health_task.done():
        return
    _health_task = asyncio.create_task(_health_loop())
    logger.info("LB health checker started")


async def stop_health_checker():
    """Stop the health check loop."""
    global _health_task
    if _health_task and not _health_task.done():
        _health_task.cancel()
        try:
            await _health_task
        except asyncio.CancelledError:
            pass
    _health_task = None
    logger.info("LB health checker stopped")


async def _health_loop():
    """Main health check loop — checks all pools on their configured interval."""
    while True:
        try:
            await _check_all_pools()
        except Exception as e:
            logger.error("Health check cycle error: %s", e)
        await asyncio.sleep(10)  # Base loop interval; per-pool intervals handled inside


async def _check_all_pools():
    """Check all active pools' backends."""
    d = await db.get_db()
    cursor = await d.execute("SELECT * FROM lb_pools WHERE active = 1")
    rows = await cursor.fetchall()

    for row in rows:
        pool = db._row_to_dict(row)
        pool_id = pool["id"]
        hc_path = pool.get("health_check_path", "/api/health")
        hc_timeout = pool.get("health_check_timeout", 5)
        max_fails = pool.get("max_fails", 3)

        cursor2 = await d.execute(
            "SELECT * FROM lb_backends WHERE pool_id = ? AND status != 'maintenance'",
            (pool_id,),
        )
        backends = await cursor2.fetchall()

        async with httpx.AsyncClient(timeout=hc_timeout) as client:
            tasks = [
                _check_backend(client, db._row_to_dict(b), hc_path, max_fails)
                for b in backends
            ]
            await asyncio.gather(*tasks, return_exceptions=True)


async def _check_backend(client: httpx.AsyncClient, backend: dict, path: str, max_fails: int):
    """Check a single backend's health."""
    backend_id = backend["id"]
    ip = backend["ip"]
    port = backend.get("port", 8000)
    url = f"http://{ip}:{port}{path}"

    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            # Healthy
            updates = {
                "failed_health_checks": 0,
                "last_health_check": datetime.utcnow().isoformat(),
            }
            if backend.get("status") == BackendStatus.UNHEALTHY.value:
                updates["status"] = BackendStatus.HEALTHY.value
                logger.info("Backend %s (%s:%d) recovered", backend_id, ip, port)
            await db.update("lb_backends", backend_id, updates)
        else:
            await _mark_failed(backend_id, backend, ip, port, max_fails, f"HTTP {resp.status_code}")

    except (httpx.RequestError, httpx.TimeoutException) as e:
        await _mark_failed(backend_id, backend, ip, port, max_fails, str(e))


async def _mark_failed(backend_id: str, backend: dict, ip: str, port: int, max_fails: int, reason: str):
    """Increment failure counter, mark unhealthy if threshold reached."""
    fails = backend.get("failed_health_checks", 0) + 1
    updates = {
        "failed_health_checks": fails,
        "last_health_check": datetime.utcnow().isoformat(),
    }

    if fails >= max_fails and backend.get("status") != BackendStatus.UNHEALTHY.value:
        updates["status"] = BackendStatus.UNHEALTHY.value
        logger.warning(
            "Backend %s (%s:%d) marked UNHEALTHY after %d fails: %s",
            backend_id, ip, port, fails, reason,
        )

    await db.update("lb_backends", backend_id, updates)
