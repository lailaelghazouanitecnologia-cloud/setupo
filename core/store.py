"""MMS Store - Async SQLite persistence layer."""
import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger("mms.store")

DB_PATH = Path("/var/lib/mms/mms.db")
_DEV_DB = Path("/tmp/mms.db")


def _db_path() -> str:
    if DB_PATH.parent.exists():
        return str(DB_PATH)
    return str(_DEV_DB)


class Store:
    def __init__(self):
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        path = _db_path()
        logger.info("Opening database at %s", path)
        self.db = await aiosqlite.connect(path)
        self.db.row_factory = aiosqlite.Row
        await self._migrate()

    async def close(self):
        if self.db:
            await self.db.close()

    async def _migrate(self):
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS capsules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                manifest TEXT NOT NULL,
                state TEXT DEFAULT 'created',
                container_id TEXT,
                pid INTEGER,
                ip TEXT,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS environments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                runtime TEXT NOT NULL,
                version TEXT DEFAULT '',
                path TEXT DEFAULT '',
                packages TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS pipelines (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                steps TEXT NOT NULL,
                state TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                results TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capsule_id TEXT NOT NULL,
                level TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_logs_capsule ON logs(capsule_id);
            CREATE INDEX IF NOT EXISTS idx_capsules_state ON capsules(state);
        """)
        await self.db.commit()

    # ── Capsules ─────────────────────────────────────────────────

    async def save_capsule(self, capsule: dict):
        await self.db.execute(
            """INSERT OR REPLACE INTO capsules
               (id, name, manifest, state, container_id, pid, ip, error, created_at, started_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                capsule["id"],
                capsule["manifest"]["name"],
                json.dumps(capsule["manifest"]),
                capsule.get("state", "created"),
                capsule.get("container_id"),
                capsule.get("pid"),
                capsule.get("ip"),
                capsule.get("error"),
                capsule.get("created_at", ""),
                capsule.get("started_at"),
                json.dumps(capsule.get("metadata", {})),
            ),
        )
        await self.db.commit()

    async def get_capsule(self, capsule_id: str) -> dict | None:
        cursor = await self.db.execute("SELECT * FROM capsules WHERE id = ?", (capsule_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_capsule(row)

    async def get_capsule_by_name(self, name: str) -> dict | None:
        cursor = await self.db.execute("SELECT * FROM capsules WHERE name = ?", (name,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_capsule(row)

    async def list_capsules(self, state: str = None) -> list[dict]:
        if state:
            cursor = await self.db.execute("SELECT * FROM capsules WHERE state = ?", (state,))
        else:
            cursor = await self.db.execute("SELECT * FROM capsules ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [self._row_to_capsule(r) for r in rows]

    async def delete_capsule(self, capsule_id: str):
        await self.db.execute("DELETE FROM capsules WHERE id = ?", (capsule_id,))
        await self.db.execute("DELETE FROM logs WHERE capsule_id = ?", (capsule_id,))
        await self.db.commit()

    async def update_capsule_state(self, capsule_id: str, state: str, **kwargs):
        sets = ["state = ?"]
        vals = [state]
        for key in ("container_id", "pid", "ip", "error", "started_at"):
            if key in kwargs:
                sets.append(f"{key} = ?")
                vals.append(kwargs[key])
        vals.append(capsule_id)
        await self.db.execute(
            f"UPDATE capsules SET {', '.join(sets)} WHERE id = ?", vals
        )
        await self.db.commit()

    @staticmethod
    def _row_to_capsule(row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "manifest": json.loads(row["manifest"]),
            "state": row["state"],
            "container_id": row["container_id"],
            "pid": row["pid"],
            "ip": row["ip"],
            "error": row["error"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
        }

    # ── Environments ─────────────────────────────────────────────

    async def save_environment(self, env: dict):
        await self.db.execute(
            """INSERT OR REPLACE INTO environments
               (id, name, runtime, version, path, packages, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                env["id"], env["name"], env["runtime"], env.get("version", ""),
                env.get("path", ""), json.dumps(env.get("packages", [])),
                env.get("created_at", ""), json.dumps(env.get("metadata", {})),
            ),
        )
        await self.db.commit()

    async def list_environments(self) -> list[dict]:
        cursor = await self.db.execute("SELECT * FROM environments ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def delete_environment(self, env_id: str):
        await self.db.execute("DELETE FROM environments WHERE id = ?", (env_id,))
        await self.db.commit()

    # ── Pipelines ────────────────────────────────────────────────

    async def save_pipeline(self, pipeline: dict):
        await self.db.execute(
            """INSERT OR REPLACE INTO pipelines (id, name, steps, state, created_at, results)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                pipeline["id"], pipeline["name"],
                json.dumps(pipeline.get("steps", [])),
                pipeline.get("state", "pending"),
                pipeline.get("created_at", ""),
                json.dumps(pipeline.get("results", {})),
            ),
        )
        await self.db.commit()

    async def list_pipelines(self) -> list[dict]:
        cursor = await self.db.execute("SELECT * FROM pipelines ORDER BY created_at DESC")
        return [dict(r) for r in await cursor.fetchall()]

    # ── Logs ─────────────────────────────────────────────────────

    async def add_log(self, capsule_id: str, message: str, level: str = "info"):
        await self.db.execute(
            "INSERT INTO logs (capsule_id, level, message) VALUES (?, ?, ?)",
            (capsule_id, level, message),
        )
        await self.db.commit()

    async def get_logs(self, capsule_id: str, limit: int = 100) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT * FROM logs WHERE capsule_id = ? ORDER BY id DESC LIMIT ?",
            (capsule_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]
