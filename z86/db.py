import json
import logging
import aiosqlite
from z86.config import settings

logger = logging.getLogger("z86.db")

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS access_keys (
    id TEXT PRIMARY KEY,
    access_key_id TEXT UNIQUE NOT NULL,
    secret_hash TEXT NOT NULL,
    secret_key TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    owner_type TEXT NOT NULL DEFAULT 'project',
    label TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    allowed_buckets TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS buckets (
    name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    region TEXT DEFAULT 'local',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    content_type TEXT DEFAULT 'application/octet-stream',
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(bucket, key),
    FOREIGN KEY (bucket) REFERENCES buckets(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_objects_bucket ON objects(bucket);
CREATE INDEX IF NOT EXISTS idx_objects_bucket_prefix ON objects(bucket, key);
CREATE INDEX IF NOT EXISTS idx_access_keys_owner ON access_keys(owner_id);
"""


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(settings.DB_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    d = await get_db()
    await d.executescript(SCHEMA)
    await d.commit()
    logger.info("z86 database initialized at %s", settings.DB_PATH)


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


# ── CRUD helpers ───────────────────────────────────────────

async def insert(table: str, data: dict) -> str:
    d = await get_db()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    await d.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(data.values()))
    await d.commit()
    return data.get("id", data.get("name", ""))


async def fetch_one(table: str, **kwargs) -> dict | None:
    d = await get_db()
    where = " AND ".join(f"{k} = ?" for k in kwargs)
    cursor = await d.execute(f"SELECT * FROM {table} WHERE {where}", list(kwargs.values()))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def fetch_all(table: str, **kwargs) -> list[dict]:
    d = await get_db()
    if kwargs:
        where = " AND ".join(f"{k} = ?" for k in kwargs)
        cursor = await d.execute(f"SELECT * FROM {table} WHERE {where}", list(kwargs.values()))
    else:
        cursor = await d.execute(f"SELECT * FROM {table}")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update(table: str, pk_col: str, pk_val: str, data: dict):
    d = await get_db()
    sets = ", ".join(f"{k} = ?" for k in data)
    vals = list(data.values()) + [pk_val]
    await d.execute(f"UPDATE {table} SET {sets} WHERE {pk_col} = ?", vals)
    await d.commit()


async def delete(table: str, **kwargs):
    d = await get_db()
    where = " AND ".join(f"{k} = ?" for k in kwargs)
    await d.execute(f"DELETE FROM {table} WHERE {where}", list(kwargs.values()))
    await d.commit()


async def count(table: str, **kwargs) -> int:
    d = await get_db()
    if kwargs:
        where = " AND ".join(f"{k} = ?" for k in kwargs)
        cursor = await d.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", list(kwargs.values()))
    else:
        cursor = await d.execute(f"SELECT COUNT(*) FROM {table}")
    row = await cursor.fetchone()
    return row[0]


async def query(sql: str, params: list | None = None) -> list[dict]:
    d = await get_db()
    cursor = await d.execute(sql, params or [])
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
