"""
Cluster management — node registration, health, and coordination.

Provides API for:
- Registering gateway/worker nodes
- Heartbeat monitoring
- Cluster topology view
- Deploy state synchronization (PostgreSQL-backed, replaces file-based fcntl)
"""

import json
import logging
import secrets
from datetime import datetime, timezone

from nso.shared import db

logger = logging.getLogger("nso.cluster")


# ── Node Registration ──

async def register_node(node_id: str, role: str, host: str, port: int = 8000, metadata: dict | None = None):
    """Register or update a cluster node."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await db.get_db()
    await conn.execute(
        """INSERT INTO cluster_nodes (node_id, role, host, port, status, last_seen, metadata)
           VALUES (?, ?, ?, ?, 'active', ?, ?)
           ON CONFLICT (node_id) DO UPDATE SET
             role = EXCLUDED.role, host = EXCLUDED.host, port = EXCLUDED.port,
             status = 'active', last_seen = EXCLUDED.last_seen, metadata = EXCLUDED.metadata""",
        (node_id, role, host, port, now, json.dumps(metadata or {})),
    )
    logger.info("Node registered: %s (%s @ %s:%d)", node_id, role, host, port)


async def heartbeat_node(node_id: str):
    """Update node heartbeat timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    conn = await db.get_db()
    await conn.execute(
        "UPDATE cluster_nodes SET last_seen = ? WHERE node_id = ?",
        (now, node_id),
    )


async def deregister_node(node_id: str):
    """Remove a node from the cluster."""
    conn = await db.get_db()
    await conn.execute("DELETE FROM cluster_nodes WHERE node_id = ?", (node_id,))
    logger.info("Node deregistered: %s", node_id)


async def list_nodes(role: str = "") -> list[dict]:
    """List all cluster nodes, optionally filtered by role."""
    if role:
        return await db.fetch_all("cluster_nodes", order_by="last_seen DESC", role=role)
    return await db.fetch_all("cluster_nodes", order_by="last_seen DESC")


async def set_node_status(node_id: str, status: str):
    """Set node status (active, draining, offline, maintenance)."""
    conn = await db.get_db()
    await conn.execute(
        "UPDATE cluster_nodes SET status = ? WHERE node_id = ?",
        (status, node_id),
    )


# ── Deploy State (PostgreSQL-backed, replaces file-based fcntl) ──

async def get_deploy_state(instance_id: str) -> dict | None:
    """Get deploy state for an instance."""
    row = await db.fetch_one("deploy_state", instance_id=instance_id)
    if not row:
        return None
    state = row.get("state", "{}")
    if isinstance(state, str):
        state = json.loads(state)
    return {
        "state": state,
        "version": row.get("version", 1),
        "target_dir": row.get("target_dir", "/opt/app"),
    }


async def save_deploy_state(
    instance_id: str,
    state: dict,
    target_dir: str = "/opt/app",
    expected_version: int | None = None,
) -> int:
    """Save deploy state with optimistic locking.

    If expected_version is provided, the update only succeeds if the
    current version matches — preventing concurrent overwrites.

    Returns the new version number.
    """
    now = datetime.now(timezone.utc).isoformat()
    state_json = json.dumps(state)
    conn = await db.get_db()

    if expected_version is not None:
        # Optimistic lock: only update if version matches
        cur = await conn.execute(
            """UPDATE deploy_state SET state = ?, target_dir = ?,
               version = version + 1, updated_at = ?
               WHERE instance_id = ? AND version = ?""",
            (state_json, target_dir, now, instance_id, expected_version),
        )
        if cur.rowcount == 0:
            # Could be a new row or a version conflict
            existing = await db.fetch_one("deploy_state", instance_id=instance_id)
            if existing:
                raise ValueError(
                    f"Concurrent modification: expected version {expected_version}, "
                    f"current is {existing.get('version')}"
                )
            # New row — insert
            await conn.execute(
                """INSERT INTO deploy_state (instance_id, target_dir, state, version, updated_at)
                   VALUES (?, ?, ?, 1, ?)""",
                (instance_id, target_dir, state_json, now),
            )
            return 1
        return expected_version + 1

    # No version check — upsert
    await conn.execute(
        """INSERT INTO deploy_state (instance_id, target_dir, state, version, updated_at)
           VALUES (?, ?, ?, 1, ?)
           ON CONFLICT (instance_id) DO UPDATE SET
             state = EXCLUDED.state, target_dir = EXCLUDED.target_dir,
             version = deploy_state.version + 1, updated_at = EXCLUDED.updated_at""",
        (instance_id, target_dir, state_json, now),
    )
    row = await db.fetch_one("deploy_state", instance_id=instance_id)
    return row["version"] if row else 1


async def delete_deploy_state(instance_id: str):
    """Remove deploy state for an instance."""
    await db.delete_where("deploy_state", instance_id=instance_id)
