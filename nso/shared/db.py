"""
NSO Database Layer — PostgreSQL via asyncpg.

Provides a high-level CRUD API + backward-compatible raw SQL interface.
All ? placeholders are auto-converted to PostgreSQL $N syntax.
"""

import json
import re
import logging
import importlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import asyncpg

from nso.config import settings

logger = logging.getLogger("nso.db")

# Connection pool
_pool: asyncpg.Pool | None = None
# Persistent connection for get_db() backward compat (raw SQL callers)
_compat_conn: asyncpg.Connection | None = None

_SAFE_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

POOL_MIN_SIZE = 2
POOL_MAX_SIZE = 10

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


# ── Placeholder conversion ──

def _q(sql: str) -> str:
    """Convert SQLite ? placeholders to PostgreSQL $N placeholders."""
    counter = [0]
    def repl(_):
        counter[0] += 1
        return f"${counter[0]}"
    return re.sub(r'\?', repl, sql)


# ── Compatibility layer ──
# Mimics aiosqlite cursor/connection API so raw SQL callers work unchanged.

class _Cursor:
    """Mimics aiosqlite cursor for backward compat."""
    __slots__ = ("_rows", "rowcount", "lastrowid")

    def __init__(self, rows=None, rowcount=0, lastrowid=None):
        self._rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _ConnWrapper:
    """Wraps asyncpg.Connection with aiosqlite-compatible execute/commit API."""

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def execute(self, sql: str, params=None):
        pg_sql = _q(sql)
        args = tuple(params) if params else ()

        upper = pg_sql.strip().upper()

        # PRAGMA statements are SQLite-only — no-op in PostgreSQL
        if upper.startswith("PRAGMA"):
            return _Cursor()

        if upper.startswith(("SELECT", "WITH")):
            rows = await self._conn.fetch(pg_sql, *args)
            return _Cursor(rows, rowcount=len(rows))

        elif upper.startswith("INSERT"):
            # Try to get lastrowid for SERIAL columns via RETURNING
            if "RETURNING" not in upper:
                try:
                    row = await self._conn.fetchrow(pg_sql + " RETURNING id", *args)
                    lastrowid = row["id"] if row else None
                    return _Cursor(rowcount=1, lastrowid=lastrowid)
                except Exception:
                    # Table might not have 'id' column, fall through
                    pass
            result = await self._conn.execute(pg_sql, *args)
            count = _parse_rowcount(result)
            return _Cursor(rowcount=count)

        else:
            # UPDATE, DELETE, DDL
            result = await self._conn.execute(pg_sql, *args)
            count = _parse_rowcount(result)
            return _Cursor(rowcount=count)

    async def executescript(self, sql: str):
        """Execute multiple semicolon-separated statements."""
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt and not stmt.startswith('--'):
                await self._conn.execute(stmt)

    async def commit(self):
        pass  # asyncpg auto-commits

    async def rollback(self):
        pass  # handled by transaction context


def _parse_rowcount(result: str) -> int:
    """Parse rowcount from asyncpg result string like 'UPDATE 3' or 'DELETE 1'."""
    if result:
        parts = result.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
    return 0


# ── Lifecycle ──

async def init_db():
    global _pool, _compat_conn
    dsn = settings.DATABASE_URL
    masked = dsn.split("@")[-1] if "@" in dsn else dsn
    logger.info("Connecting to PostgreSQL: %s (pool %d-%d)", masked, POOL_MIN_SIZE, POOL_MAX_SIZE)

    _pool = await asyncpg.create_pool(dsn, min_size=POOL_MIN_SIZE, max_size=POOL_MAX_SIZE)
    _compat_conn = await asyncpg.connect(dsn)

    # Run all module migrations
    wrapper = _ConnWrapper(_compat_conn)
    await _run_module_migrations(wrapper)

    logger.info("PostgreSQL ready — migrations complete")


async def close_db():
    global _pool, _compat_conn
    if _compat_conn:
        await _compat_conn.close()
        _compat_conn = None
    if _pool:
        await _pool.close()
        _pool = None


async def get_db():
    """Get the persistent connection wrapper (for backward compat with raw SQL)."""
    if _compat_conn is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _ConnWrapper(_compat_conn)


async def _migrate(conn):
    """Alias for test compatibility."""
    wrapper = conn if isinstance(conn, _ConnWrapper) else _ConnWrapper(conn)
    return await _run_module_migrations(wrapper)


async def _run_module_migrations(conn: _ConnWrapper):
    engine_dir = Path(__file__).parent.parent / "engine"
    if not engine_dir.exists():
        logger.warning("Engine directory not found at %s", engine_dir)
        return

    for module_dir in sorted(engine_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        mig_file = module_dir / "migrations.py"
        if not mig_file.exists():
            continue
        mod_name = module_dir.name
        mod = importlib.import_module(f"nso.engine.{mod_name}.migrations")
        if hasattr(mod, "TABLES") and mod.TABLES.strip():
            await conn.executescript(mod.TABLES)
        if hasattr(mod, "INDEXES") and mod.INDEXES.strip():
            await conn.executescript(mod.INDEXES)
        if hasattr(mod, "run_alterations"):
            await mod.run_alterations(conn, logger)

    logger.info("Database migrations complete")


# ── Serialization ──

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


def row_to_dict(row) -> dict:
    """Convert asyncpg Record or dict to dict with JSON/bool deserialization."""
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


# ── CRUD operations (use connection pool) ──

async def insert(table: str, data: dict):
    _validate_identifier(table, "table")
    for k in data:
        _validate_identifier(k, "column")
    cols = ", ".join(data.keys())
    n = len(data)
    placeholders = ", ".join(f"${i+1}" for i in range(n))
    vals = [_serialize_value(v) for v in data.values()]

    async with _pool.acquire() as conn:
        await conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", *vals)


async def update(table: str, id_val: str, data: dict):
    _validate_identifier(table, "table")
    for k in data:
        _validate_identifier(k, "column")
    sets = [f"{k} = ${i+1}" for i, k in enumerate(data)]
    vals = [_serialize_value(v) for v in data.values()]
    vals.append(id_val)
    id_ph = f"${len(data) + 1}"

    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE {table} SET {', '.join(sets)} WHERE id = {id_ph}", *vals
        )


async def fetch_one(table: str, **where) -> dict | None:
    """Read a single row. Uses connection pool."""
    _validate_identifier(table, "table")
    for k in where:
        _validate_identifier(k, "column")
    conditions = " AND ".join(f"{k} = ${i+1}" for i, k in enumerate(where))

    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT * FROM {table} WHERE {conditions}",
            *list(where.values()),
        )
    if not row:
        return None
    return row_to_dict(row)


async def fetch_all(table: str, order_by: str = "created_at DESC", **where) -> list[dict]:
    """Read multiple rows. Uses connection pool."""
    _validate_identifier(table, "table")
    _validate_order_by(order_by)
    for k in where:
        _validate_identifier(k, "column")

    async with _pool.acquire() as conn:
        if where:
            conditions = " AND ".join(f"{k} = ${i+1}" for i, k in enumerate(where))
            rows = await conn.fetch(
                f"SELECT * FROM {table} WHERE {conditions} ORDER BY {order_by}",
                *list(where.values()),
            )
        else:
            rows = await conn.fetch(f"SELECT * FROM {table} ORDER BY {order_by}")
    return [row_to_dict(r) for r in rows]


async def delete(table: str, id_val: str):
    _validate_identifier(table, "table")
    async with _pool.acquire() as conn:
        await conn.execute(f"DELETE FROM {table} WHERE id = $1", id_val)


async def delete_where(table: str, **where):
    _validate_identifier(table, "table")
    for k in where:
        _validate_identifier(k, "column")
    conditions = " AND ".join(f"{k} = ${i+1}" for i, k in enumerate(where))

    async with _pool.acquire() as conn:
        await conn.execute(
            f"DELETE FROM {table} WHERE {conditions}",
            *list(where.values()),
        )


# ── Atomic transactions ──

@asynccontextmanager
async def transaction():
    """Execute multiple operations atomically.

    Usage:
        async with db.transaction() as conn:
            await conn.execute("UPDATE ...", ...)
            await conn.execute("INSERT ...", ...)
        # auto-commits on exit, rolls back on exception
    """
    async with _pool.acquire() as conn:
        async with conn.transaction():
            yield _ConnWrapper(conn)
