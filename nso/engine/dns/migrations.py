TABLES = """
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
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_domains_project ON domains(project_id);
    CREATE INDEX IF NOT EXISTS idx_domains_instance ON domains(instance_id);
"""
