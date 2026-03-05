"""
Monitor — collect metrics from agents via HTTP polling.
Runs as a background task every POLL_INTERVAL seconds.
"""
import asyncio
import logging
from datetime import datetime

import httpx

from nso.shared import db
from nso.engine.orchestrator.models import NodeMetrics, NodeStatus, ScaleAlert
from nso.engine.orchestrator import pool

logger = logging.getLogger("nso.orchestrator.monitor")

POLL_INTERVAL = 60  # seconds
AGENT_PORT = 8081
AGENT_TIMEOUT = 10  # seconds

# Alert thresholds
CPU_WARNING = 70.0
CPU_CRITICAL = 90.0
MEM_WARNING = 75.0
MEM_CRITICAL = 90.0
DISK_WARNING = 80.0
DISK_CRITICAL = 95.0

_monitor_task: asyncio.Task | None = None


async def start_monitor():
    """Start the background monitoring loop."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        logger.debug("Monitor already running")
        return
    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("Orchestrator monitor started (interval=%ds)", POLL_INTERVAL)


async def stop_monitor():
    """Stop the monitoring loop."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    _monitor_task = None
    logger.info("Orchestrator monitor stopped")


async def _monitor_loop():
    """Main monitoring loop."""
    while True:
        try:
            await _collect_all_metrics()
        except Exception as e:
            logger.error("Monitor cycle error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def _collect_all_metrics():
    """Collect metrics from all active pool nodes."""
    nodes = await pool.list_nodes(status="active")
    if not nodes:
        return

    async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
        tasks = [_collect_node_metrics(client, node) for node in nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for node, result in zip(nodes, results):
        if isinstance(result, Exception):
            logger.warning("Failed to collect metrics from %s (%s): %s", node.id, node.ip, result)
            # Mark as offline after 3 missed heartbeats
            if node.last_heartbeat:
                try:
                    last = datetime.fromisoformat(node.last_heartbeat)
                    elapsed = (datetime.utcnow() - last).total_seconds()
                    if elapsed > POLL_INTERVAL * 3:
                        await db.update("instance_pool", node.id, {"status": NodeStatus.OFFLINE.value})
                        logger.warning("Node %s marked offline (no heartbeat for %ds)", node.id, int(elapsed))
                except Exception:
                    pass


async def _collect_node_metrics(client: httpx.AsyncClient, node) -> NodeMetrics | None:
    """Collect metrics from a single node's agent."""
    if not node.ip:
        return None

    # Use agent exec endpoint to get system metrics
    agent_url = f"http://{node.ip}:{AGENT_PORT}"

    try:
        # Get system metrics via exec
        resp = await client.post(
            f"{agent_url}/exec/",
            json={
                "command": (
                    "python3 -c \""
                    "import json, os;"
                    "st = os.statvfs('/');"
                    "disk_total = st.f_blocks * st.f_frsize;"
                    "disk_free = st.f_bavail * st.f_frsize;"
                    "disk_pct = round((1 - disk_free/disk_total) * 100, 1) if disk_total else 0;"
                    "with open('/proc/stat') as f: cpu_line = f.readline();"
                    "vals = list(map(int, cpu_line.split()[1:]));"
                    "idle = vals[3]; total = sum(vals);"
                    "with open('/proc/meminfo') as f: lines = f.readlines()[:3];"
                    "mem = {};"
                    "[mem.update({l.split(':')[0].strip(): int(l.split(':')[1].strip().split()[0])}) for l in lines];"
                    "mem_total = mem.get('MemTotal', 1);"
                    "mem_avail = mem.get('MemAvailable', mem.get('MemFree', 0));"
                    "mem_pct = round((1 - mem_avail/mem_total) * 100, 1);"
                    "la = os.getloadavg();"
                    "with open('/proc/uptime') as f: uptime = int(float(f.read().split()[0]));"
                    "print(json.dumps({'cpu': round((1-idle/total)*100 if total else 0, 1),"
                    "'mem': mem_pct, 'disk': disk_pct,"
                    "'la1': round(la[0],2), 'la5': round(la[1],2), 'la15': round(la[2],2),"
                    "'uptime': uptime}))\""
                ),
                "timeout": 5,
            },
            headers=_agent_auth_header(node),
        )

        if resp.status_code != 200:
            logger.debug("Agent exec failed on %s: %s", node.id, resp.status_code)
            return None

        import json
        data = resp.json()
        output = data.get("output", "").strip()
        metrics_data = json.loads(output)

        metrics = NodeMetrics(
            node_id=node.id,
            cpu_percent=metrics_data.get("cpu", 0),
            mem_percent=metrics_data.get("mem", 0),
            disk_percent=metrics_data.get("disk", 0),
            load_avg_1m=metrics_data.get("la1", 0),
            load_avg_5m=metrics_data.get("la5", 0),
            load_avg_15m=metrics_data.get("la15", 0),
            uptime_seconds=metrics_data.get("uptime", 0),
        )

        # Update pool node metrics
        await pool.update_node_metrics(
            node.id,
            cpu=metrics.cpu_percent,
            mem=metrics.mem_percent,
            disk=metrics.disk_percent,
        )

        # Check thresholds and generate alerts
        await _check_alerts(node, metrics)

        return metrics

    except httpx.RequestError as e:
        raise RuntimeError(f"Agent unreachable at {node.ip}: {e}")


def _agent_auth_header(node) -> dict:
    """Build auth header for agent. Uses metadata.agent_token if set."""
    token = (node.metadata or {}).get("agent_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _check_alerts(node, metrics: NodeMetrics):
    """Check metrics against thresholds and store alerts."""
    import secrets as _secrets

    alerts_to_create = []

    if metrics.cpu_percent >= CPU_CRITICAL:
        alerts_to_create.append(("high_cpu", "critical", metrics.cpu_percent, CPU_CRITICAL,
                                 f"CPU at {metrics.cpu_percent}% on {node.label or node.id}"))
    elif metrics.cpu_percent >= CPU_WARNING:
        alerts_to_create.append(("high_cpu", "warning", metrics.cpu_percent, CPU_WARNING,
                                 f"CPU at {metrics.cpu_percent}% on {node.label or node.id}"))

    if metrics.mem_percent >= MEM_CRITICAL:
        alerts_to_create.append(("high_mem", "critical", metrics.mem_percent, MEM_CRITICAL,
                                 f"Memory at {metrics.mem_percent}% on {node.label or node.id}"))
    elif metrics.mem_percent >= MEM_WARNING:
        alerts_to_create.append(("high_mem", "warning", metrics.mem_percent, MEM_WARNING,
                                 f"Memory at {metrics.mem_percent}% on {node.label or node.id}"))

    if metrics.disk_percent >= DISK_CRITICAL:
        alerts_to_create.append(("high_disk", "critical", metrics.disk_percent, DISK_CRITICAL,
                                 f"Disk at {metrics.disk_percent}% on {node.label or node.id}"))
    elif metrics.disk_percent >= DISK_WARNING:
        alerts_to_create.append(("high_disk", "warning", metrics.disk_percent, DISK_WARNING,
                                 f"Disk at {metrics.disk_percent}% on {node.label or node.id}"))

    for alert_type, severity, value, threshold, message in alerts_to_create:
        alert_id = f"alert_{_secrets.token_hex(8)}"
        await db.insert("orchestrator_alerts", {
            "id": alert_id,
            "node_id": node.id,
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            "value": value,
            "threshold": threshold,
            "resolved": 0,
        })


async def get_active_alerts(node_id: str | None = None) -> list[ScaleAlert]:
    """Get unresolved alerts, optionally for a specific node."""
    d = await db.get_db()
    if node_id:
        cursor = await d.execute(
            "SELECT * FROM orchestrator_alerts WHERE node_id = ? AND resolved = 0 ORDER BY created_at DESC",
            (node_id,),
        )
    else:
        cursor = await d.execute(
            "SELECT * FROM orchestrator_alerts WHERE resolved = 0 ORDER BY created_at DESC LIMIT 100"
        )
    rows = await cursor.fetchall()
    return [ScaleAlert(**db._row_to_dict(r)) for r in rows]


async def resolve_alert(alert_id: str):
    """Mark an alert as resolved."""
    await db.update("orchestrator_alerts", alert_id, {
        "resolved": 1,
        "resolved_at": datetime.utcnow().isoformat(),
    })
