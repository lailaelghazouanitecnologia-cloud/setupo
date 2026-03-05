TABLES = """
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
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger_blocks(user_id);
    CREATE INDEX IF NOT EXISTS idx_ledger_user_idx ON ledger_blocks(user_id, idx);
    CREATE INDEX IF NOT EXISTS idx_ledger_type ON ledger_blocks(block_type);
    CREATE INDEX IF NOT EXISTS idx_ledger_hash ON ledger_blocks(hash);
    CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log(action);
    CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
    CREATE INDEX IF NOT EXISTS idx_snapshots_type ON analytics_snapshots(snapshot_type);
    CREATE INDEX IF NOT EXISTS idx_snapshots_created ON analytics_snapshots(created_at);
"""
