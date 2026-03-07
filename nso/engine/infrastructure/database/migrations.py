TABLES = """
    CREATE TABLE IF NOT EXISTS managed_databases (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        instance_id TEXT NOT NULL,
        name TEXT NOT NULL,
        engine TEXT DEFAULT 'postgresql',
        version TEXT DEFAULT '16',
        host TEXT DEFAULT '',
        port INTEGER DEFAULT 5432,
        db_user TEXT DEFAULT '',
        password_encrypted TEXT DEFAULT '',
        state TEXT DEFAULT 'creating',
        size_mb REAL DEFAULT 0,
        max_connections INTEGER DEFAULT 100,
        error TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        ready_at TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_managed_databases_project ON managed_databases(project_id);
    CREATE INDEX IF NOT EXISTS idx_managed_databases_instance ON managed_databases(instance_id);
"""
