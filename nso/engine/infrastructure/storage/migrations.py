TABLES = """
    CREATE TABLE IF NOT EXISTS storage_buckets (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        r2_prefix TEXT NOT NULL,
        size_bytes INTEGER DEFAULT 0,
        object_count INTEGER DEFAULT 0,
        public_access INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, name)
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_storage_buckets_project ON storage_buckets(project_id);
"""
