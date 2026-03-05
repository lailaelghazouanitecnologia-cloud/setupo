TABLES = """
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
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
    CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
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
"""
