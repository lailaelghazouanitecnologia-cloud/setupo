import json
import logging
from datetime import datetime

import aiosqlite

from server.config import settings

logger = logging.getLogger("nso.db")

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
    await _db.execute("PRAGMA foreign_keys = ON")
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
            author TEXT DEFAULT 'nso',
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

        CREATE TABLE IF NOT EXISTS addon_catalog (
            id TEXT PRIMARY KEY,
            addon_id TEXT NOT NULL,
            addon_type TEXT NOT NULL DEFAULT 'plugin',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            version TEXT DEFAULT '1.0.0',
            category TEXT DEFAULT '',
            icon TEXT DEFAULT '',
            author TEXT DEFAULT 'nso',
            published INTEGER DEFAULT 1,
            config_schema TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS addons (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            addon_id TEXT NOT NULL,
            addon_type TEXT NOT NULL DEFAULT 'plugin',
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
        CREATE INDEX IF NOT EXISTS idx_addon_catalog_type ON addon_catalog(addon_type);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_addon_catalog_unique ON addon_catalog(addon_id, addon_type);
        CREATE INDEX IF NOT EXISTS idx_addon_catalog_published ON addon_catalog(published);
        CREATE INDEX IF NOT EXISTS idx_addons_project ON addons(project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_addons_unique ON addons(project_id, addon_id, addon_type);
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

        CREATE TABLE IF NOT EXISTS ledger_blocks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            block_type TEXT NOT NULL,
            amount_cents INTEGER DEFAULT 0,
            balance_after_cents INTEGER DEFAULT 0,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            nonce TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS analytics_snapshots (
            id TEXT PRIMARY KEY,
            snapshot_type TEXT DEFAULT 'full',
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger_blocks(user_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_user_idx ON ledger_blocks(user_id, idx);
        CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger_blocks(block_type);
        CREATE INDEX IF NOT EXISTS idx_ledger_hash ON ledger_blocks(hash);
        CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log(action);
        CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_snapshots_type ON analytics_snapshots(snapshot_type);
        CREATE INDEX IF NOT EXISTS idx_snapshots_created ON analytics_snapshots(created_at);

        CREATE TABLE IF NOT EXISTS email_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            purpose TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            expires_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_email_tokens_hash ON email_tokens(token_hash);
        CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id);

        CREATE TABLE IF NOT EXISTS project_secrets (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            bucket TEXT DEFAULT 'custom',
            scope TEXT DEFAULT 'general',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_project_secrets_project ON project_secrets(project_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_secrets_unique ON project_secrets(project_id, key, scope);
        CREATE INDEX IF NOT EXISTS idx_project_secrets_scope ON project_secrets(project_id, scope);

        CREATE TABLE IF NOT EXISTS instance_pool (
            id TEXT PRIMARY KEY,
            instance_id TEXT NOT NULL UNIQUE,
            label TEXT DEFAULT '',
            role TEXT DEFAULT 'hybrid',
            status TEXT DEFAULT 'active',
            ip TEXT,
            region TEXT DEFAULT 'ewr',
            plan TEXT DEFAULT 'vc2-1c-1gb',
            max_concurrent_builds INTEGER DEFAULT 2,
            cpu_percent REAL DEFAULT 0.0,
            mem_percent REAL DEFAULT 0.0,
            disk_percent REAL DEFAULT 0.0,
            active_builds INTEGER DEFAULT 0,
            last_heartbeat TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS build_queue (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            workspace TEXT NOT NULL,
            branch TEXT DEFAULT 'main',
            assigned_node_id TEXT,
            status TEXT DEFAULT 'queued',
            priority INTEGER DEFAULT 0,
            build_command TEXT DEFAULT 'npm run build',
            logs TEXT DEFAULT '',
            error TEXT,
            metadata TEXT DEFAULT '{}',
            queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (assigned_node_id) REFERENCES instance_pool(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS orchestrator_alerts (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT DEFAULT 'warning',
            message TEXT DEFAULT '',
            value REAL DEFAULT 0.0,
            threshold REAL DEFAULT 0.0,
            resolved INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            FOREIGN KEY (node_id) REFERENCES instance_pool(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_pool_instance ON instance_pool(instance_id);
        CREATE INDEX IF NOT EXISTS idx_pool_role ON instance_pool(role);
        CREATE INDEX IF NOT EXISTS idx_pool_status ON instance_pool(status);
        CREATE INDEX IF NOT EXISTS idx_build_queue_status ON build_queue(status);
        CREATE INDEX IF NOT EXISTS idx_build_queue_project ON build_queue(project_id);
        CREATE INDEX IF NOT EXISTS idx_build_queue_node ON build_queue(assigned_node_id);
        CREATE INDEX IF NOT EXISTS idx_build_queue_queued ON build_queue(queued_at);
        CREATE INDEX IF NOT EXISTS idx_orch_alerts_node ON orchestrator_alerts(node_id);
        CREATE INDEX IF NOT EXISTS idx_orch_alerts_resolved ON orchestrator_alerts(resolved);

        CREATE TABLE IF NOT EXISTS lb_pools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            project_id TEXT DEFAULT '',
            algorithm TEXT DEFAULT 'round_robin',
            health_check_path TEXT DEFAULT '/api/health',
            health_check_interval INTEGER DEFAULT 30,
            health_check_timeout INTEGER DEFAULT 5,
            max_fails INTEGER DEFAULT 3,
            sticky_sessions INTEGER DEFAULT 0,
            sticky_cookie TEXT DEFAULT 'NSO_LB_SID',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lb_backends (
            id TEXT PRIMARY KEY,
            pool_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            ip TEXT NOT NULL,
            port INTEGER DEFAULT 8000,
            weight INTEGER DEFAULT 1,
            status TEXT DEFAULT 'healthy',
            active_connections INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            failed_health_checks INTEGER DEFAULT 0,
            last_health_check TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pool_id) REFERENCES lb_pools(id) ON DELETE CASCADE,
            FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lb_rules (
            id TEXT PRIMARY KEY,
            pool_id TEXT NOT NULL,
            match_type TEXT DEFAULT 'prefix',
            match_value TEXT DEFAULT '/',
            priority INTEGER DEFAULT 0,
            headers TEXT DEFAULT '{}',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pool_id) REFERENCES lb_pools(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_lb_pools_active ON lb_pools(active);
        CREATE INDEX IF NOT EXISTS idx_lb_pools_project ON lb_pools(project_id);
        CREATE INDEX IF NOT EXISTS idx_lb_backends_pool ON lb_backends(pool_id);
        CREATE INDEX IF NOT EXISTS idx_lb_backends_status ON lb_backends(status);
        CREATE INDEX IF NOT EXISTS idx_lb_backends_instance ON lb_backends(instance_id);
        CREATE INDEX IF NOT EXISTS idx_lb_rules_pool ON lb_rules(pool_id);
        CREATE INDEX IF NOT EXISTS idx_lb_rules_priority ON lb_rules(priority);

        -- z86 storage: access keys managed by central server
        CREATE TABLE IF NOT EXISTS z86_keys (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            access_key_id TEXT UNIQUE NOT NULL,
            secret_access_key TEXT NOT NULL,
            label TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            bucket TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_z86_keys_project ON z86_keys(project_id);
    """)

    # Migration: add workspace columns
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
            except Exception as e:
                logger.debug("Migration skip (workspaces.%s): %s", col, e)

    # Migration: add subdomain column
    try:
        await db.execute("SELECT subdomain FROM users LIMIT 1")
    except Exception:
        try:
            await db.execute("ALTER TABLE users ADD COLUMN subdomain TEXT UNIQUE")
        except Exception as e:
            logger.warning("Migration failed (users.subdomain): %s", e)

    # Migration: add last_active column
    try:
        await db.execute("SELECT last_active FROM users LIMIT 1")
    except Exception:
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_active TEXT")
        except Exception as e:
            logger.warning("Migration failed (users.last_active): %s", e)

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


import re as _re
_SAFE_IDENT = _re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str, kind: str = "identifier"):
    """Validate SQL identifier to prevent injection via table/column names."""
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid SQL {kind}: {name!r}")


def _validate_order_by(order_by: str):
    """Validate ORDER BY clause — only allows 'column ASC/DESC' patterns."""
    for part in order_by.split(","):
        tokens = part.strip().split()
        if not tokens or len(tokens) > 2:
            raise ValueError(f"Invalid ORDER BY: {order_by!r}")
        _validate_identifier(tokens[0], "column")
        if len(tokens) == 2 and tokens[1].upper() not in ("ASC", "DESC"):
            raise ValueError(f"Invalid ORDER BY direction: {tokens[1]!r}")


async def insert(table: str, data: dict):
    _validate_identifier(table, "table")
    for k in data:
        _validate_identifier(k, "column")
    db = await get_db()
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    vals = [_serialize_value(v) for v in data.values()]
    await db.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", vals)
    await db.commit()


async def update(table: str, id_val: str, data: dict):
    _validate_identifier(table, "table")
    for k in data:
        _validate_identifier(k, "column")
    db = await get_db()
    sets = [f"{k} = ?" for k in data]
    vals = [_serialize_value(v) for v in data.values()]
    vals.append(id_val)
    await db.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()


async def fetch_one(table: str, **where) -> dict | None:
    _validate_identifier(table, "table")
    for k in where:
        _validate_identifier(k, "column")
    db = await get_db()
    conditions = " AND ".join(f"{k} = ?" for k in where)
    cursor = await db.execute(f"SELECT * FROM {table} WHERE {conditions}", list(where.values()))
    row = await cursor.fetchone()
    if not row:
        return None
    return _row_to_dict(row)


async def fetch_all(table: str, order_by: str = "created_at DESC", **where) -> list[dict]:
    _validate_identifier(table, "table")
    _validate_order_by(order_by)
    for k in where:
        _validate_identifier(k, "column")
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
    _validate_identifier(table, "table")
    db = await get_db()
    await db.execute(f"DELETE FROM {table} WHERE id = ?", (id_val,))
    await db.commit()


async def delete_where(table: str, **where):
    _validate_identifier(table, "table")
    for k in where:
        _validate_identifier(k, "column")
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
