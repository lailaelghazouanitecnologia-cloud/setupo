"""
Scaler — analyze pool load and generate scaling recommendations.
"""
import logging
from datetime import datetime, timedelta

from nso.shared import db
from nso.engine.orchestrator.models import LoadLevel, PoolOverview, ScaleAlert
from nso.engine.orchestrator import pool
from nso.engine.orchestrator.monitor import get_active_alerts

logger = logging.getLogger("nso.orchestrator.scaler")


def _load_level(percent: float) -> LoadLevel:
    if percent < 40:
        return LoadLevel.LOW
    if percent < 70:
        return LoadLevel.MEDIUM
    if percent < 90:
        return LoadLevel.HIGH
    return LoadLevel.CRITICAL


async def get_pool_overview() -> PoolOverview:
    """Get full pool overview with aggregated metrics."""
    nodes = await pool.list_nodes()
    active_nodes = [n for n in nodes if n.status.value == "active"]

    builders = len([n for n in nodes if n.role.value in ("builder", "hybrid")])
    runners = len([n for n in nodes if n.role.value in ("runner", "hybrid")])

    avg_cpu = sum(n.cpu_percent for n in active_nodes) / len(active_nodes) if active_nodes else 0
    avg_mem = sum(n.mem_percent for n in active_nodes) / len(active_nodes) if active_nodes else 0

    # Build stats
    d = await db.get_db()
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    cursor = await d.execute("SELECT COUNT(*) FROM build_queue WHERE status = 'queued'")
    queued = (await cursor.fetchone())[0]

    cursor = await d.execute("SELECT COUNT(*) FROM build_queue WHERE status IN ('assigned', 'building')")
    active_builds = (await cursor.fetchone())[0]

    cursor = await d.execute("SELECT COUNT(*) FROM build_queue WHERE status = 'done' AND finished_at > ?", (cutoff,))
    completed_24h = (await cursor.fetchone())[0]

    cursor = await d.execute("SELECT COUNT(*) FROM build_queue WHERE status = 'failed' AND finished_at > ?", (cutoff,))
    failed_24h = (await cursor.fetchone())[0]

    alerts = await get_active_alerts()

    return PoolOverview(
        total_nodes=len(nodes),
        active_nodes=len(active_nodes),
        builders=builders,
        runners=runners,
        avg_cpu=round(avg_cpu, 1),
        avg_mem=round(avg_mem, 1),
        queued_builds=queued,
        active_builds=active_builds,
        completed_builds_24h=completed_24h,
        failed_builds_24h=failed_24h,
        alerts=alerts,
        nodes=nodes,
    )


async def get_recommendations() -> list[dict]:
    """Generate scaling recommendations based on current state."""
    overview = await get_pool_overview()
    recs = []

    # High average CPU
    if overview.avg_cpu >= 80 and overview.active_nodes > 0:
        recs.append({
            "type": "scale_up",
            "reason": f"Average CPU is {overview.avg_cpu}% across {overview.active_nodes} nodes",
            "action": "Add a builder node to distribute build load",
            "severity": "critical" if overview.avg_cpu >= 90 else "warning",
        })

    # High average memory
    if overview.avg_mem >= 80 and overview.active_nodes > 0:
        recs.append({
            "type": "scale_up",
            "reason": f"Average memory is {overview.avg_mem}% across {overview.active_nodes} nodes",
            "action": "Add more RAM or a new node",
            "severity": "critical" if overview.avg_mem >= 90 else "warning",
        })

    # Build queue backlog
    if overview.queued_builds > 3:
        recs.append({
            "type": "scale_up",
            "reason": f"{overview.queued_builds} builds waiting in queue",
            "action": "Add a builder node or increase max_concurrent_builds",
            "severity": "warning",
        })

    # No builders available
    if overview.builders == 0 and overview.total_nodes > 0:
        recs.append({
            "type": "config",
            "reason": "No nodes with builder role",
            "action": "Change at least one node role to 'builder' or 'hybrid'",
            "severity": "critical",
        })

    # Underutilized nodes
    low_nodes = [n for n in overview.nodes if n.status.value == "active" and n.cpu_percent < 10 and n.active_builds == 0]
    if len(low_nodes) > 1:
        recs.append({
            "type": "scale_down",
            "reason": f"{len(low_nodes)} nodes are idle (CPU < 10%)",
            "action": "Consider removing idle nodes to reduce costs",
            "severity": "info",
        })

    # High failure rate
    total_recent = overview.completed_builds_24h + overview.failed_builds_24h
    if total_recent > 5 and overview.failed_builds_24h / total_recent > 0.3:
        recs.append({
            "type": "investigate",
            "reason": f"{overview.failed_builds_24h}/{total_recent} builds failed in 24h ({int(overview.failed_builds_24h/total_recent*100)}%)",
            "action": "Check build logs for recurring errors",
            "severity": "warning",
        })

    return recs


async def get_node_history(node_id: str, hours: int = 24) -> list[dict]:
    """Get recent build history for a specific node."""
    d = await db.get_db()
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    cursor = await d.execute(
        """SELECT id, project_id, workspace, status, started_at, finished_at, error
           FROM build_queue
           WHERE assigned_node_id = ? AND queued_at > ?
           ORDER BY queued_at DESC""",
        (node_id, cutoff),
    )
    rows = await cursor.fetchall()
    return [db._row_to_dict(r) for r in rows]
