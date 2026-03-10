TABLES = """
    CREATE TABLE IF NOT EXISTS deploy_logs (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        instance_id TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_deploy_logs_instance ON deploy_logs(instance_id);
"""
