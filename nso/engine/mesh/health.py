"""
NSO Mesh — Background health monitor.

Periodically checks SSH connectivity to all registered devices
and updates their status (online/offline) in the database.
"""

import asyncio
import logging
from datetime import datetime

from nso.shared import db
from nso.engine.compute.provisioner import run_ssh_command
from nso.engine.mesh.service import get_master_key_path

logger = logging.getLogger("nso.mesh.health")

HEALTH_INTERVAL = 30          # seconds between health checks
OFFLINE_THRESHOLD = 3         # consecutive failures before marking offline
METRICS_INTERVAL = 300        # seconds between full metrics collection

_task: asyncio.Task | None = None
_fail_counts: dict[str, int] = {}


async def _check_device(device: dict, key_path: str) -> bool:
    """Check if a device is reachable via SSH. Returns True if alive."""
    try:
        output, code = await run_ssh_command(
            device["host"], "echo ok", key_path,
            user=device["ssh_user"], timeout=10,
        )
        return code == 0 and "ok" in output
    except Exception as e:
        logger.debug("Health check failed for %s: %s", device["name"], e)
        return False


async def _collect_metrics(device: dict, key_path: str) -> dict | None:
    """Collect system metrics from a device."""
    cmd = (
        "cat /proc/loadavg 2>/dev/null; "
        "free -m 2>/dev/null | awk 'NR==2{print $2,$3}'; "
        "df -m / 2>/dev/null | awk 'NR==2{print $2,$3}'"
    )
    try:
        output, code = await run_ssh_command(
            device["host"], cmd, key_path,
            user=device["ssh_user"], timeout=15,
        )
        if code != 0:
            return None
        return {"raw": output.strip()}
    except Exception:
        return None


async def _health_loop():
    """Main health check loop."""
    cycle = 0
    while True:
        try:
            await asyncio.sleep(HEALTH_INTERVAL)
            cycle += 1
            do_metrics = (cycle % (METRICS_INTERVAL // HEALTH_INTERVAL)) == 0

            conn = await db.get_db()
            cursor = await conn.execute(
                "SELECT * FROM mesh_devices WHERE status IN ('online', 'offline')"
            )
            rows = await cursor.fetchall()
            devices = [db.row_to_dict(r) for r in rows]

            if not devices:
                continue

            key_path = get_master_key_path()

            for device in devices:
                did = device["id"]
                alive = await _check_device(device, key_path)
                now = datetime.utcnow().isoformat()

                if alive:
                    _fail_counts[did] = 0
                    update = {"last_seen_at": now}

                    if device["status"] == "offline":
                        update["status"] = "online"
                        logger.info("Device %s (%s) came back online",
                                    device["name"], device["host"])

                    if do_metrics:
                        metrics = await _collect_metrics(device, key_path)
                        if metrics:
                            update["os_info"] = {
                                **(device.get("os_info") or {}),
                                "metrics": metrics,
                                "collected_at": now,
                            }

                    await db.update("mesh_devices", did, update)
                else:
                    _fail_counts[did] = _fail_counts.get(did, 0) + 1

                    if (_fail_counts[did] >= OFFLINE_THRESHOLD
                            and device["status"] == "online"):
                        await db.update("mesh_devices", did, {
                            "status": "offline",
                            "updated_at": now,
                        })
                        logger.warning("Device %s (%s) marked offline after %d failures",
                                       device["name"], device["host"], _fail_counts[did])

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Mesh health check error: %s", e)
            await asyncio.sleep(5)


async def start_mesh_health():
    """Start the mesh health monitor background task."""
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_health_loop())
    logger.info("Mesh health monitor started (interval=%ds)", HEALTH_INTERVAL)


async def stop_mesh_health():
    """Stop the mesh health monitor."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    _fail_counts.clear()
    logger.info("Mesh health monitor stopped")
