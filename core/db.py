import json
import logging
from datetime import datetime

import aiosqlite

from server.config import settings

logger = logging.getLogger("setupo.db")

_db: aiosqlite.Connection | None = None


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
    await _migrate(_db)


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def _migrate(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key_hash TEXT NOT NULL UNIQUE,
            owner TEXT DEFAULT '',
            settings TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS instances (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            type TEXT DEFAULT 'setup',
            provider TEXT DEFAULT 'vultr',
            provider_id TEXT DEFAULT '',
            label TEXT DEFAULT '',
            region TEXT DEFAULT 'ewr',
            plan TEXT DEFAULT 'vc2-1c-1gb',
            os_id INTEGER DEFAULT 2284,
            ip TEXT,
            domain TEXT,
            state TEXT DEFAULT 'creating',
            ssh_key_id TEXT,
            workspace TEXT,
            error TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            ready_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            ws_type TEXT DEFAULT 'custom',
            stack TEXT DEFAULT '',
            description TEXT DEFAULT '',
            instance_id TEXT,
            git_url TEXT,
            branch TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS domains (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            record_type TEXT DEFAULT 'A',
            value TEXT DEFAULT '',
            cf_zone_id TEXT,
            cf_record_id TEXT,
            proxied INTEGER DEFAULT 0,
            managed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS deploy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS plugin_catalog (
            id TEXT PRIMARY KEY,
            plugin_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            version TEXT DEFAULT '1.0.0',
            category TEXT DEFAULT '',
            icon TEXT DEFAULT '',
            author TEXT DEFAULT 'setupo',
            published INTEGER DEFAULT 1,
            config_schema TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS plugins (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            plugin_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            version TEXT DEFAULT '1.0.0',
            category TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            config TEXT DEFAULT '{}',
            installed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            balance REAL DEFAULT 0.00,
            verified INTEGER DEFAULT 0,
            subdomain TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT DEFAULT '',
            reference TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS modules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            version TEXT DEFAULT '1.0.0',
            category TEXT DEFAULT 'core',
            r2_key TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            hash TEXT DEFAULT '',
            published INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_instances_project ON instances(project_id);
        CREATE INDEX IF NOT EXISTS idx_instances_state ON instances(state);
        CREATE INDEX IF NOT EXISTS idx_workspaces_project ON workspaces(project_id);
        CREATE INDEX IF NOT EXISTS idx_domains_project ON domains(project_id);
        CREATE INDEX IF NOT EXISTS idx_domains_instance ON domains(instance_id);
        CREATE INDEX IF NOT EXISTS idx_deploy_logs_instance ON deploy_logs(instance_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_name ON workspaces(project_id, name);
        CREATE INDEX IF NOT EXISTS idx_plugins_project ON plugins(project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_plugins_unique ON plugins(project_id, plugin_id);
        CREATE INDEX IF NOT EXISTS idx_plugin_catalog_published ON plugin_catalog(published);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_plans (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            interval TEXT DEFAULT 'monthly',
            amount_cents INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            features TEXT DEFAULT '{}',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS billing_subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            plan_code TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            current_period_start TEXT,
            current_period_end TEXT,
            amount_cents INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            cancelled_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES billing_plans(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS billing_invoices (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            subscription_id TEXT,
            number TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            payment_status TEXT DEFAULT 'pending',
            currency TEXT DEFAULT 'USD',
            subtotal_cents INTEGER DEFAULT 0,
            credits_applied_cents INTEGER DEFAULT 0,
            total_cents INTEGER DEFAULT 0,
            period_start TEXT,
            period_end TEXT,
            due_date TEXT,
            finalized_at TEXT,
            paid_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_invoice_items (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            type TEXT DEFAULT 'subscription',
            description TEXT DEFAULT '',
            units REAL DEFAULT 1,
            unit_price_cents INTEGER DEFAULT 0,
            amount_cents INTEGER DEFAULT 0,
            metric TEXT,
            FOREIGN KEY (invoice_id) REFERENCES billing_invoices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_payment_methods (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT DEFAULT 'card',
            provider TEXT DEFAULT 'stripe',
            provider_id TEXT DEFAULT '',
            label TEXT DEFAULT '',
            is_default INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_usage_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            metric TEXT NOT NULL,
            units REAL DEFAULT 0,
            transaction_id TEXT,
            properties TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_coupons (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            coupon_type TEXT DEFAULT 'percentage',
            value INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            frequency TEXT DEFAULT 'once',
            frequency_duration INTEGER DEFAULT 0,
            plan_codes TEXT DEFAULT '[]',
            max_redemptions INTEGER DEFAULT 0,
            redemptions_count INTEGER DEFAULT 0,
            amount_cents_remaining INTEGER DEFAULT 0,
            expires_at TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS billing_applied_coupons (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            coupon_id TEXT NOT NULL,
            subscription_id TEXT,
            status TEXT DEFAULT 'active',
            amount_cents_used INTEGER DEFAULT 0,
            periods_remaining INTEGER DEFAULT 0,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (coupon_id) REFERENCES billing_coupons(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_credit_notes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            invoice_id TEXT,
            number TEXT NOT NULL,
            reason TEXT DEFAULT '',
            credit_type TEXT DEFAULT 'refund',
            status TEXT DEFAULT 'available',
            total_cents INTEGER DEFAULT 0,
            balance_cents INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'USD',
            items TEXT DEFAULT '[]',
            refund_status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            voided_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (invoice_id) REFERENCES billing_invoices(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS billing_billable_metrics (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            aggregation_type TEXT DEFAULT 'sum',
            field_name TEXT DEFAULT '',
            recurring INTEGER DEFAULT 0,
            filters TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS billing_taxes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            rate REAL DEFAULT 0.0,
            description TEXT DEFAULT '',
            applied_to TEXT DEFAULT 'all',
            region TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS billing_wallets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT DEFAULT 'Primary',
            currency TEXT DEFAULT 'USD',
            balance_cents INTEGER DEFAULT 0,
            consumed_cents INTEGER DEFAULT 0,
            rate_amount REAL DEFAULT 1.0,
            credits_balance REAL DEFAULT 0.0,
            credits_consumed REAL DEFAULT 0.0,
            status TEXT DEFAULT 'active',
            expiration_at TEXT,
            priority INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            depleted_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_wallet_transactions (
            id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            transaction_type TEXT DEFAULT 'inbound',
            amount REAL DEFAULT 0.0,
            credit_amount REAL DEFAULT 0.0,
            source TEXT DEFAULT '',
            settled_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wallet_id) REFERENCES billing_wallets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            user_id TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_modules_name ON modules(name);
        CREATE INDEX IF NOT EXISTS idx_modules_published ON modules(published);
        CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(user_id, read);
        CREATE INDEX IF NOT EXISTS idx_billing_subs_user ON billing_subscriptions(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_subs_status ON billing_subscriptions(status);
        CREATE INDEX IF NOT EXISTS idx_billing_inv_user ON billing_invoices(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_inv_status ON billing_invoices(status);
        CREATE INDEX IF NOT EXISTS idx_billing_items_invoice ON billing_invoice_items(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_billing_pm_user ON billing_payment_methods(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_usage_user ON billing_usage_events(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_usage_metric ON billing_usage_events(metric);
        CREATE INDEX IF NOT EXISTS idx_billing_coupons_code ON billing_coupons(code);
        CREATE INDEX IF NOT EXISTS idx_billing_coupons_active ON billing_coupons(active);
        CREATE INDEX IF NOT EXISTS idx_billing_applied_coupons_user ON billing_applied_coupons(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_applied_coupons_sub ON billing_applied_coupons(subscription_id);
        CREATE INDEX IF NOT EXISTS idx_billing_credit_notes_user ON billing_credit_notes(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_credit_notes_inv ON billing_credit_notes(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_billing_metrics_code ON billing_billable_metrics(code);
        CREATE INDEX IF NOT EXISTS idx_billing_taxes_code ON billing_taxes(code);
        CREATE INDEX IF NOT EXISTS idx_billing_wallets_user ON billing_wallets(user_id);
        CREATE INDEX IF NOT EXISTS idx_billing_wallet_txn ON billing_wallet_transactions(wallet_id);
        CREATE INDEX IF NOT EXISTS idx_billing_events_type ON billing_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_billing_events_resource ON billing_events(resource_type, resource_id);
        CREATE INDEX IF NOT EXISTS idx_billing_events_user ON billing_events(user_id);
    """)

    try:
        await db.execute("SELECT ws_type FROM workspaces LIMIT 1")
    except Exception:
        for col, default in [
            ("ws_type", "'custom'"),
            ("stack", "''"),
            ("description", "''"),
            ("instance_id", "NULL"),
            ("updated_at", "CURRENT_TIMESTAMP"),
        ]:
            try:
                await db.execute(f"ALTER TABLE workspaces ADD COLUMN {col} TEXT DEFAULT {default}")
            except Exception:
                pass

    try:
        await db.execute("SELECT subdomain FROM users LIMIT 1")
    except Exception:
        try:
            await db.execute("ALTER TABLE users ADD COLUMN subdomain TEXT UNIQUE")
        except Exception:
            pass

    await db.commit()
    logger.info("Database migrations complete")


def _serialize_value(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bool):
        return int(v)
    return v


async def insert(table: str, data: dict):
    db = await get_db()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    vals = [_serialize_value(v) for v in data.values()]
    await db.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", vals)
    await db.commit()


async def update(table: str, id_val: str, data: dict):
    db = await get_db()
    sets = [f"{k} = ?" for k in data]
    vals = [_serialize_value(v) for v in data.values()]
    vals.append(id_val)
    await db.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()


async def fetch_one(table: str, **where) -> dict | None:
    db = await get_db()
    conditions = " AND ".join(f"{k} = ?" for k in where)
    cursor = await db.execute(f"SELECT * FROM {table} WHERE {conditions}", list(where.values()))
    row = await cursor.fetchone()
    if not row:
        return None
    return _row_to_dict(row)


async def fetch_all(table: str, order_by: str = "created_at DESC", **where) -> list[dict]:
    db = await get_db()
    if where:
        conditions = " AND ".join(f"{k} = ?" for k in where)
        cursor = await db.execute(
            f"SELECT * FROM {table} WHERE {conditions} ORDER BY {order_by}",
            list(where.values()),
        )
    else:
        cursor = await db.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def delete(table: str, id_val: str):
    db = await get_db()
    await db.execute(f"DELETE FROM {table} WHERE id = ?", (id_val,))
    await db.commit()


async def delete_where(table: str, **where):
    db = await get_db()
    conditions = " AND ".join(f"{k} = ?" for k in where)
    await db.execute(f"DELETE FROM {table} WHERE {conditions}", list(where.values()))
    await db.commit()


JSON_FIELDS = frozenset({"settings", "metadata", "config", "config_schema", "features", "properties", "plan_codes", "items", "data", "filters"})
BOOL_FIELDS = frozenset({"proxied", "managed", "enabled", "published", "verified", "read", "is_default", "active", "recurring"})


def _row_to_dict(row: aiosqlite.Row) -> dict:
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
