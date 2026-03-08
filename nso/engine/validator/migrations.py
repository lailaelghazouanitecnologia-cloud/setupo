"""
Validator — database schema.

Tables:
  validations        — check definitions (templates, reusable)
  validation_runs    — execution runs (group of checks)
  validation_results — individual check results per run
"""

TABLES = """
    CREATE TABLE IF NOT EXISTS validations (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        type TEXT NOT NULL DEFAULT 'http',
        config TEXT NOT NULL DEFAULT '{}',
        metadata TEXT DEFAULT '{}',
        enabled INTEGER DEFAULT 1,
        created_by TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, name)
    );

    CREATE TABLE IF NOT EXISTS validation_runs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace TEXT DEFAULT '',
        instance_id TEXT DEFAULT '',
        trigger TEXT DEFAULT 'manual',
        status TEXT DEFAULT 'running',
        total INTEGER DEFAULT 0,
        passed INTEGER DEFAULT 0,
        failed INTEGER DEFAULT 0,
        skipped INTEGER DEFAULT 0,
        duration_ms INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS validation_results (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        validation_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        duration_ms INTEGER DEFAULT 0,
        output TEXT DEFAULT '',
        error TEXT DEFAULT '',
        config TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES validation_runs(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_validations_project ON validations(project_id);
    CREATE INDEX IF NOT EXISTS idx_validation_runs_project ON validation_runs(project_id);
    CREATE INDEX IF NOT EXISTS idx_validation_runs_status ON validation_runs(status);
    CREATE INDEX IF NOT EXISTS idx_validation_results_run ON validation_results(run_id);
    CREATE INDEX IF NOT EXISTS idx_validation_results_status ON validation_results(status);
"""
