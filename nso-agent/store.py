import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from models import (
    Stage,
    StageInfo,
    InstanceMetrics,
    MetricReport,
    STAGE_ORDER,
    STAGE_PROGRESS,
)

logger = logging.getLogger("nso-agent.store")

DB_PATH = Path("/opt/setupo/data/metrics.db")
DEV_DB_PATH = Path("/tmp/setupo/metrics.db")
MAX_LOG_ENTRIES = 500

_db: aiosqlite.Connection | None = None


def _resolve_path() -> Path:
    if DB_PATH.parent.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return DB_PATH
    DEV_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEV_DB_PATH


async def init():
    global _db
    path = _resolve_path()
    logger.info("Opening metrics DB at %s", path)
    _db = await aiosqlite.connect(str(path))
    _db.row_factory = aiosqlite.Row
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS instance_metrics (
            instance_id TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            current_stage TEXT DEFAULT 'booting',
            progress INTEGER DEFAULT 0,
            stages TEXT DEFAULT '[]',
            logs TEXT DEFAULT '[]',
            started_at TEXT,
            finished_at TEXT,
            error TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_updated
            ON instance_metrics(updated_at);
    """)
    await _db.commit()


async def close():
    global _db
    if _db:
        await _db.close()
        _db = None


async def count_tracked() -> int:
    cursor = await _db.execute("SELECT COUNT(*) FROM instance_metrics")
    row = await cursor.fetchone()
    return row[0] if row else 0


def _build_initial_stages() -> list[dict]:
    return [
        StageInfo(name=stage.value).model_dump()
        for stage, _ in STAGE_ORDER
    ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def register_instance(instance_id: str, token: str):
    now = _now()
    stages = _build_initial_stages()
    await _db.execute(
        """INSERT OR REPLACE INTO instance_metrics
           (instance_id, token, current_stage, progress, stages, logs, started_at, updated_at)
           VALUES (?, ?, 'booting', 0, ?, '[]', ?, ?)""",
        (instance_id, token, json.dumps(stages), now, now),
    )
    await _db.commit()


async def verify_token(instance_id: str, token: str) -> bool:
    cursor = await _db.execute(
        "SELECT token FROM instance_metrics WHERE instance_id = ?",
        (instance_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return False
    return row["token"] == token


async def report(data: MetricReport) -> InstanceMetrics:
    cursor = await _db.execute(
        "SELECT * FROM instance_metrics WHERE instance_id = ?",
        (data.instance_id,),
    )
    row = await cursor.fetchone()
    if not row:
        await register_instance(data.instance_id, data.token)
        cursor = await _db.execute(
            "SELECT * FROM instance_metrics WHERE instance_id = ?",
            (data.instance_id,),
        )
        row = await cursor.fetchone()

    now = _now()
    stages = json.loads(row["stages"])
    logs = json.loads(row["logs"])

    stage_progress = STAGE_PROGRESS.get(data.stage, data.progress)
    progress = max(stage_progress, data.progress)

    for s in stages:
        if s["name"] == data.stage.value:
            if s["status"] == "pending":
                s["status"] = "in_progress"
                s["started_at"] = now
            s["message"] = data.message
            if data.stage in (Stage.READY, Stage.ERROR):
                s["status"] = "done" if data.stage == Stage.READY else "error"
                s["finished_at"] = now
                if s["started_at"]:
                    started = datetime.fromisoformat(s["started_at"])
                    finished = datetime.fromisoformat(now)
                    s["duration_s"] = round((finished - started).total_seconds(), 1)
            break

    stage_names = [st.value for st, _ in STAGE_ORDER]
    current_idx = stage_names.index(data.stage.value) if data.stage.value in stage_names else -1
    for i, s in enumerate(stages):
        if i < current_idx and s["status"] in ("pending", "in_progress"):
            s["status"] = "done"
            if not s["finished_at"]:
                s["finished_at"] = now

    log_entry = f"{now} [{data.stage.value}] {data.message}"
    logs.append(log_entry)
    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[-MAX_LOG_ENTRIES:]

    finished_at = row["finished_at"]
    error = row["error"]
    if data.stage == Stage.READY:
        finished_at = now
    if data.stage == Stage.ERROR or data.error:
        error = data.error or data.message
        for s in stages:
            if s["name"] == data.stage.value:
                s["status"] = "error"

    await _db.execute(
        """UPDATE instance_metrics SET
           current_stage = ?, progress = ?, stages = ?, logs = ?,
           finished_at = ?, error = ?, updated_at = ?
           WHERE instance_id = ?""",
        (
            data.stage.value, progress, json.dumps(stages), json.dumps(logs),
            finished_at, error, now, data.instance_id,
        ),
    )
    await _db.commit()

    return await get_metrics(data.instance_id)


async def get_metrics(instance_id: str) -> InstanceMetrics | None:
    cursor = await _db.execute(
        "SELECT * FROM instance_metrics WHERE instance_id = ?",
        (instance_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    row = dict(row)
    stages = json.loads(row["stages"])
    logs = json.loads(row["logs"])

    elapsed = 0.0
    estimated = 0.0
    if row["started_at"]:
        started = datetime.fromisoformat(row["started_at"])
        if row["finished_at"]:
            finished = datetime.fromisoformat(row["finished_at"])
            elapsed = (finished - started).total_seconds()
        else:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            progress = row["progress"] or 1
            if progress > 0:
                total_estimated = elapsed / (progress / 100)
                estimated = max(0, total_estimated - elapsed)

    return InstanceMetrics(
        instance_id=row["instance_id"],
        current_stage=row["current_stage"],
        progress=row["progress"],
        stages=[StageInfo(**s) for s in stages],
        logs=logs,
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        elapsed_s=round(elapsed, 1),
        estimated_remaining_s=round(estimated, 1),
        error=row["error"],
    )


async def delete_metrics(instance_id: str):
    await _db.execute(
        "DELETE FROM instance_metrics WHERE instance_id = ?",
        (instance_id,),
    )
    await _db.commit()
