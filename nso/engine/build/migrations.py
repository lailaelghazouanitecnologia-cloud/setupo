TABLES = """
    CREATE TABLE IF NOT EXISTS build_cache (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        artifact_r2_key TEXT NOT NULL,
        artifact_size INTEGER DEFAULT 0,
        build_command TEXT DEFAULT '',
        stack TEXT DEFAULT '',
        built_on TEXT DEFAULT 'server',
        duration_s REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS build_logs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        built_on TEXT DEFAULT 'server',
        output TEXT DEFAULT '',
        duration_s REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_build_cache_project ON build_cache(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_build_cache_lookup ON build_cache(project_id, workspace, source_hash);
    CREATE INDEX IF NOT EXISTS idx_build_logs_project ON build_logs(project_id);
    CREATE INDEX IF NOT EXISTS idx_build_logs_hash ON build_logs(project_id, workspace, source_hash);
"""
