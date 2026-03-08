TABLES = """
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
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS instance_metrics (
        id TEXT PRIMARY KEY,
        instance_id TEXT NOT NULL UNIQUE,
        ip TEXT DEFAULT '',
        reachable INTEGER DEFAULT 0,
        cpu_percent REAL DEFAULT 0,
        mem_percent REAL DEFAULT 0,
        mem_used_mb INTEGER DEFAULT 0,
        mem_total_mb INTEGER DEFAULT 0,
        disk_percent REAL DEFAULT 0,
        disk_used_gb REAL DEFAULT 0,
        disk_total_gb REAL DEFAULT 0,
        load_1m REAL DEFAULT 0,
        uptime INTEGER DEFAULT 0,
        history TEXT DEFAULT '[]',
        collected_at TEXT DEFAULT '',
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_instances_project ON instances(project_id);
    CREATE INDEX IF NOT EXISTS idx_instances_state ON instances(state);
    CREATE INDEX IF NOT EXISTS idx_instances_project_state ON instances(project_id, state);
    CREATE INDEX IF NOT EXISTS idx_instance_metrics_instance ON instance_metrics(instance_id);
"""
