#!/usr/bin/env python3
"""
NSO — SQLite to PostgreSQL Data Migration

Migrates all table data from an existing SQLite database to PostgreSQL.
The target PostgreSQL database should already have the schema created
(NSO creates tables automatically on startup).

Usage:
    python3 migrate-sqlite-to-pg.py --sqlite /opt/nso/data/nso.db --pg postgresql://nso:pass@localhost:5432/nso

Options:
    --sqlite PATH       Path to source SQLite database
    --pg DSN            PostgreSQL connection string
    --tables TABLE,...  Only migrate specific tables (comma-separated)
    --skip TABLE,...    Skip specific tables
    --dry-run           Show what would be migrated without writing
    --batch-size N      Rows per INSERT batch (default: 500)
"""

import argparse
import asyncio
import json
import sqlite3
import sys
import time


async def migrate(sqlite_path: str, pg_dsn: str, tables: list[str] | None = None,
                  skip: list[str] | None = None, dry_run: bool = False,
                  batch_size: int = 500):
    import asyncpg

    skip = set(skip or [])
    skip.add("sqlite_sequence")  # SQLite internal

    print(f"\n{'DRY RUN — ' if dry_run else ''}SQLite → PostgreSQL Migration")
    print(f"  Source: {sqlite_path}")
    print(f"  Target: {pg_dsn.split('@')[-1] if '@' in pg_dsn else pg_dsn}")
    print()

    # ── Connect to SQLite ──
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    # Get all SQLite tables
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    all_tables = [row[0] for row in cursor.fetchall()]

    if tables:
        all_tables = [t for t in all_tables if t in tables]

    all_tables = [t for t in all_tables if t not in skip]

    print(f"  Tables to migrate: {len(all_tables)}")
    print()

    # ── Connect to PostgreSQL ──
    pg_conn = await asyncpg.connect(pg_dsn)

    # Get existing PostgreSQL tables
    pg_tables = set()
    rows = await pg_conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    for row in rows:
        pg_tables.add(row["table_name"])

    # ── Determine migration order (respect foreign keys) ──
    # Tables without foreign keys first, then tables that depend on them
    ordered = _topological_sort(sqlite_conn, all_tables)

    total_rows = 0
    total_skipped = 0
    errors = []

    for table in ordered:
        if table not in pg_tables:
            print(f"  SKIP {table} (not in PostgreSQL — run NSO once first to create schema)")
            total_skipped += 1
            continue

        # Count rows
        count = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if count == 0:
            print(f"  {table}: 0 rows (empty)")
            continue

        # Check if PG table already has data
        pg_count = await pg_conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
        if pg_count > 0:
            print(f"  {table}: {pg_count} rows already in PG — SKIPPING (use --skip to override)")
            continue

        # Get columns from SQLite
        sqlite_cols = sqlite_conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        col_names = [col[1] for col in sqlite_cols]
        col_types = {col[1]: col[2].upper() for col in sqlite_cols}

        # Get columns from PostgreSQL
        pg_cols_rows = await pg_conn.fetch(
            "SELECT column_name, is_identity FROM information_schema.columns "
            "WHERE table_name = $1 ORDER BY ordinal_position", table
        )
        pg_col_names = set(r["column_name"] for r in pg_cols_rows)
        pg_identity_cols = set(r["column_name"] for r in pg_cols_rows if r["is_identity"] == "ALWAYS")

        # Filter to columns that exist in both, excluding IDENTITY columns
        migrate_cols = [c for c in col_names if c in pg_col_names and c not in pg_identity_cols]

        if not migrate_cols:
            print(f"  {table}: no matching columns — SKIPPING")
            continue

        if dry_run:
            print(f"  {table}: {count} rows, {len(migrate_cols)} columns (dry run)")
            total_rows += count
            continue

        # ── Migrate in batches ──
        print(f"  {table}: migrating {count} rows ({len(migrate_cols)} cols)...", end="", flush=True)
        start = time.time()
        migrated = 0

        placeholders = ", ".join(f"${i+1}" for i in range(len(migrate_cols)))
        cols_str = ", ".join(f'"{c}"' for c in migrate_cols)
        insert_sql = f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

        offset = 0
        while offset < count:
            rows = sqlite_conn.execute(
                f'SELECT * FROM "{table}" LIMIT {batch_size} OFFSET {offset}'
            ).fetchall()

            batch = []
            for row in rows:
                row_dict = dict(row)
                values = []
                for col in migrate_cols:
                    val = row_dict.get(col)
                    # Convert Python types for asyncpg
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", errors="replace")
                    values.append(val)
                batch.append(tuple(values))

            if batch:
                try:
                    await pg_conn.executemany(insert_sql, batch)
                    migrated += len(batch)
                except Exception as e:
                    # Try row-by-row for better error reporting
                    for i, row_vals in enumerate(batch):
                        try:
                            await pg_conn.execute(insert_sql, *row_vals)
                            migrated += 1
                        except Exception as row_err:
                            errors.append(f"{table} row {offset + i}: {row_err}")

            offset += batch_size

        elapsed = time.time() - start
        rate = migrated / elapsed if elapsed > 0 else 0
        print(f" {migrated}/{count} rows ({elapsed:.1f}s, {rate:.0f} rows/s)")
        total_rows += migrated

    await pg_conn.close()
    sqlite_conn.close()

    # ── Summary ──
    print()
    print(f"{'DRY RUN ' if dry_run else ''}Migration complete:")
    print(f"  Rows migrated:  {total_rows}")
    print(f"  Tables skipped: {total_skipped}")
    if errors:
        print(f"  Errors:         {len(errors)}")
        for err in errors[:20]:
            print(f"    - {err}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20} more")
    print()

    return len(errors) == 0


def _topological_sort(sqlite_conn, tables: list[str]) -> list[str]:
    """Sort tables so referenced tables come before referencing tables."""
    table_set = set(tables)
    deps: dict[str, set[str]] = {t: set() for t in tables}

    for table in tables:
        fks = sqlite_conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        for fk in fks:
            referenced = fk[2]  # table name
            if referenced in table_set:
                deps[table].add(referenced)

    # Kahn's algorithm
    in_degree = {t: 0 for t in tables}
    for t, d in deps.items():
        for dep in d:
            if t in in_degree:  # only count if both exist
                in_degree[t] += 1 if dep in in_degree else 0

    # Recount properly
    in_degree = {t: 0 for t in tables}
    graph = {t: [] for t in tables}
    for t, d in deps.items():
        for dep in d:
            if dep in graph:
                graph[dep].append(t)
                in_degree[t] += 1

    queue = [t for t in tables if in_degree[t] == 0]
    result = []

    while queue:
        queue.sort()  # deterministic order
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Add any remaining (circular deps)
    for t in tables:
        if t not in result:
            result.append(t)

    return result


def main():
    parser = argparse.ArgumentParser(description="Migrate NSO data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Path to SQLite database")
    parser.add_argument("--pg", required=True, help="PostgreSQL DSN (postgresql://user:pass@host/db)")
    parser.add_argument("--tables", default="", help="Only migrate these tables (comma-separated)")
    parser.add_argument("--skip", default="", help="Skip these tables (comma-separated)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without migrating")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch (default: 500)")
    args = parser.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or None
    skip = [t.strip() for t in args.skip.split(",") if t.strip()] or None

    success = asyncio.run(migrate(
        sqlite_path=args.sqlite,
        pg_dsn=args.pg,
        tables=tables,
        skip=skip,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
