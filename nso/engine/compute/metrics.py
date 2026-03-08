"""
Instance metrics collector — polls agent /metrics/summary endpoints
and stores time-series data for dashboard display.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx

from nso.shared import db
from nso.config import settings

logger = logging.getLogger("nso.compute.metrics")

POLL_INTERVAL = 30  # seconds
MAX_HISTORY = 720   # ~6 hours at 30s interval
_task: asyncio.Task | None = None


async def _get_agent_token(ip: str) -> str | None:
    """Authenticate with agent and get JWT token."""
    agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "") or getattr(settings, "AGENT_ADMIN_PASSWORD", "")
    if not agent_password:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"http://{ip}:8081/auth/login", json={
                "email": settings.ADMIN_EMAIL,
                "password": agent_password,
            })
            if resp.status_code == 200:
                return resp.json().get("token")
    except Exception:
        pass
    return None


async def _poll_instance(instance: dict) -> dict | None:
    """Poll a single instance for metrics."""
    ip = instance.get("ip")
    if not ip:
        return None

    token = await _get_agent_token(ip)
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"http://{ip}:8081/metrics/summary",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                data["instance_id"] = instance["id"]
                data["ip"] = ip
                data["collected_at"] = datetime.now(timezone.utc).isoformat()
                data["reachable"] = True
                return data
    except Exception as e:
        logger.debug("Failed to poll %s (%s): %s", instance.get("label", ""), ip, e)

    return {
        "instance_id": instance["id"],
        "ip": ip,
        "reachable": False,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


async def _poll_all():
    """Poll all active instances and store metrics."""
    all_instances = await db.fetch_all("instances")
    instances = [
        i for i in all_instances
        if i.get("state") in ("running", "ready", "active")
        and i.get("ip")
    ]
    if not instances:
        return

    # Poll instances concurrently (max 10 at a time)
    sem = asyncio.Semaphore(10)

    async def poll_with_sem(inst):
        async with sem:
            return await _poll_instance(inst)

    tasks = [poll_with_sem(inst) for inst in instances]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ts = int(time.time())
    for result in results:
        if isinstance(result, Exception) or result is None:
            continue

        instance_id = result["instance_id"]

        # Store latest snapshot
        existing = await db.fetch_one("instance_metrics", instance_id=instance_id)
        snapshot = {
            "instance_id": instance_id,
            "ip": result.get("ip", ""),
            "reachable": 1 if result.get("reachable") else 0,
            "cpu_percent": result.get("cpu_percent", 0),
            "mem_percent": result.get("mem_percent", 0),
            "mem_used_mb": result.get("mem_used_mb", 0),
            "mem_total_mb": result.get("mem_total_mb", 0),
            "disk_percent": result.get("disk_percent", 0),
            "disk_used_gb": result.get("disk_used_gb", 0),
            "disk_total_gb": result.get("disk_total_gb", 0),
            "load_1m": result.get("load_1m", 0),
            "uptime": result.get("uptime", 0),
            "collected_at": result.get("collected_at", ""),
        }

        if existing:
            # Append to history ring buffer
            history = json.loads(existing.get("history", "[]"))
            history.append({
                "ts": ts,
                "cpu": result.get("cpu_percent", 0),
                "mem": result.get("mem_percent", 0),
                "disk": result.get("disk_percent", 0),
                "load": result.get("load_1m", 0),
            })
            # Trim history
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]
            snapshot["history"] = json.dumps(history)
            await db.update("instance_metrics", existing["id"], snapshot)
        else:
            import uuid
            snapshot["id"] = f"im_{uuid.uuid4().hex[:16]}"
            snapshot["history"] = json.dumps([{
                "ts": ts,
                "cpu": result.get("cpu_percent", 0),
                "mem": result.get("mem_percent", 0),
                "disk": result.get("disk_percent", 0),
                "load": result.get("load_1m", 0),
            }])
            await db.insert("instance_metrics", snapshot)


async def _collector_loop():
    """Background loop that polls metrics periodically."""
    logger.info("Metrics collector started (interval=%ds)", POLL_INTERVAL)
    while True:
        try:
            await _poll_all()
        except Exception as e:
            logger.error("Metrics poll error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


def start_collector():
    """Start the background metrics collector task."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_collector_loop())
        logger.info("Metrics collector task started")


def stop_collector():
    """Stop the background metrics collector task."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        _task = None


# --- API functions (called by routes) ---

async def get_instance_metrics(project_id: str, instance_id: str) -> dict | None:
    """Get latest metrics + history for a specific instance."""
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst or inst.get("project_id") != project_id:
        return None

    metrics = await db.fetch_one("instance_metrics", instance_id=instance_id)
    if not metrics:
        return {"instance_id": instance_id, "available": False}

    result = dict(metrics)
    result["available"] = True
    result["reachable"] = bool(result.get("reachable"))
    # Parse history for frontend
    try:
        result["history"] = json.loads(result.get("history", "[]"))
    except Exception:
        result["history"] = []
    return result


async def get_project_metrics(project_id: str) -> list[dict]:
    """Get metrics summary for all instances in a project."""
    instances = await db.fetch_all("instances", project_id=project_id)
    result = []
    for inst in instances:
        metrics = await db.fetch_one("instance_metrics", instance_id=inst["id"])
        entry = {
            "instance_id": inst["id"],
            "label": inst.get("label", ""),
            "state": inst.get("state", ""),
            "ip": inst.get("ip", ""),
            "workspace": inst.get("workspace", ""),
        }
        if metrics:
            entry.update({
                "reachable": bool(metrics.get("reachable")),
                "cpu_percent": metrics.get("cpu_percent", 0),
                "mem_percent": metrics.get("mem_percent", 0),
                "disk_percent": metrics.get("disk_percent", 0),
                "load_1m": metrics.get("load_1m", 0),
                "uptime": metrics.get("uptime", 0),
                "collected_at": metrics.get("collected_at", ""),
            })
        else:
            entry["reachable"] = False
        result.append(entry)
    return result
