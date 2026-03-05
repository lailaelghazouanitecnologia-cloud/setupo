TABLES = """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        api_key_hash TEXT NOT NULL UNIQUE,
        owner TEXT DEFAULT '',
        settings TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

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
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_project_secrets_project ON project_secrets(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_project_secrets_unique ON project_secrets(project_id, key, scope);
    CREATE INDEX IF NOT EXISTS idx_project_secrets_scope ON project_secrets(project_id, scope);
"""
