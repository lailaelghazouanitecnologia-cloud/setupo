import json
import re
import logging
import importlib
from datetime import datetime
from pathlib import Path

import aiosqlite

from nso.config import settings

logger = logging.getLogger("nso.db")

_db: aiosqlite.Connection | None = None

_SAFE_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

JSON_FIELDS = frozenset({
    "settings", "metadata", "config", "config_schema",
    "features", "properties", "plan_codes", "items",
    "data", "filters", "protected_files", "headers",
    "tool_calls", "tool_results", "history", "depends_on",
    "endpoints", "connects_to", "dependencies", "env",
    "tunnel_config", "tags", "capabilities", "labels", "os_info",
    "placement_node_selector", "placement_affinity",
    "placement_anti_affinity_services", "placement_anti_affinity_nodes",
    "auto_provision",
})
BOOL_FIELDS = frozenset({
    "proxied", "managed", "enabled", "published",
    "verified", "read", "is_default", "active", "recurring",
    "agent_visible", "readonly", "reachable", "auto_renew",
    "auto_deploy", "sticky_sessions", "notify_slack", "notify_email",
})


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def init_db():
    global _db
    path = str(settings.db_path())
    logger.info("Opening database at %s", path)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA foreign_keys = ON")
    await _run_module_migrations(_db)


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def _migrate(conn: aiosqlite.Connection):
    """Alias for test compatibility."""
    return await _run_module_migrations(conn)


async def _run_module_migrations(conn: aiosqlite.Connection):
    engine_dir = Path(__file__).parent.parent / "engine"
    if not engine_dir.exists():
        logger.warning("Engine directory not found at %s", engine_dir)
        await conn.commit()
        return

    for module_dir in sorted(engine_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        mig_file = module_dir / "migrations.py"
        if not mig_file.exists():
            continue
        mod_name = module_dir.name
        mod = importlib.import_module(f"nso.engine.{mod_name}.migrations")
        if hasattr(mod, "TABLES"):
            await conn.executescript(mod.TABLES)
        if hasattr(mod, "INDEXES"):
            await conn.executescript(mod.INDEXES)
        if hasattr(mod, "run_alterations"):
            await mod.run_alterations(conn, logger)

    await conn.commit()
    logger.info("Database migrations complete")


def _serialize_value(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    return v


def _validate_identifier(name: str, kind: str = "identifier"):
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid SQL {kind}: {name!r}")


def _validate_order_by(order_by: str):
    for part in order_by.split(","):
        tokens = part.strip().split()
        if not tokens or len(tokens) > 2:
            raise ValueError(f"Invalid ORDER BY: {order_by!r}")
        _validate_identifier(tokens[0], "column")
        if len(tokens) == 2 and tokens[1].upper() not in ("ASC", "DESC"):
            raise ValueError(f"Invalid ORDER BY direction: {tokens[1]!r}")


def row_to_dict(row: aiosqlite.Row) -> dict:
    d = dict(row)
    for key in JSON_FIELDS:
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    for key in BOOL_FIELDS:
        if key in d and isinstance(d[key], int):
            d[key] = bool(d[key])
    return d


async def insert(table: str, data: dict):
    _validate_identifier(table, "table")
    for k in data:
        _validate_identifier(k, "column")
    conn = await get_db()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    vals = [_serialize_value(v) for v in data.values()]
    await conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", vals)
    await conn.commit()


async def update(table: str, id_val: str, data: dict):
    _validate_identifier(table, "table")
    for k in data:
        _validate_identifier(k, "column")
    conn = await get_db()
    sets = [f"{k} = ?" for k in data]
    vals = [_serialize_value(v) for v in data.values()]
    vals.append(id_val)
    await conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", vals)
    await conn.commit()


async def fetch_one(table: str, **where) -> dict | None:
    _validate_identifier(table, "table")
    for k in where:
        _validate_identifier(k, "column")
    conn = await get_db()
    conditions = " AND ".join(f"{k} = ?" for k in where)
    cursor = await conn.execute(f"SELECT * FROM {table} WHERE {conditions}", list(where.values()))
    row = await cursor.fetchone()
    if not row:
        return None
    return row_to_dict(row)


async def fetch_all(table: str, order_by: str = "created_at DESC", **where) -> list[dict]:
    _validate_identifier(table, "table")
    _validate_order_by(order_by)
    for k in where:
        _validate_identifier(k, "column")
    conn = await get_db()
    if where:
        conditions = " AND ".join(f"{k} = ?" for k in where)
        cursor = await conn.execute(
            f"SELECT * FROM {table} WHERE {conditions} ORDER BY {order_by}",
            list(where.values()),
        )
    else:
        cursor = await conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
    rows = await cursor.fetchall()
    return [row_to_dict(r) for r in rows]


async def delete(table: str, id_val: str):
    _validate_identifier(table, "table")
    conn = await get_db()
    await conn.execute(f"DELETE FROM {table} WHERE id = ?", (id_val,))
    await conn.commit()


async def delete_where(table: str, **where):
    _validate_identifier(table, "table")
    for k in where:
        _validate_identifier(k, "column")
    conn = await get_db()
    conditions = " AND ".join(f"{k} = ?" for k in where)
    await conn.execute(f"DELETE FROM {table} WHERE {conditions}", list(where.values()))
    await conn.commit()
