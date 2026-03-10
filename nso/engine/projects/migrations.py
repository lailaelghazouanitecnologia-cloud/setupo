TABLES = """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        api_key_hash TEXT NOT NULL UNIQUE,
        owner TEXT DEFAULT NULL,
        settings TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner) REFERENCES users(id) ON DELETE SET NULL
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

    CREATE TABLE IF NOT EXISTS project_members (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        invited_by TEXT DEFAULT '',
        join_code TEXT DEFAULT '',
        joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(project_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS project_invites (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        join_code TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL DEFAULT 'viewer',
        max_uses INTEGER DEFAULT 0,
        uses INTEGER DEFAULT 0,
        created_by TEXT DEFAULT '',
        expires_at TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
"""

async def run_alterations(conn, logger):
    """Convert empty string owners to NULL for FK compatibility."""
    try:
        await conn.execute("UPDATE projects SET owner = NULL WHERE owner = ''")
    except Exception:
        pass  # Table might not have data yet


INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_project_secrets_project ON project_secrets(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_project_secrets_unique ON project_secrets(project_id, key, scope);
    CREATE INDEX IF NOT EXISTS idx_project_secrets_scope ON project_secrets(project_id, scope);
    CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);
    CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
    CREATE INDEX IF NOT EXISTS idx_project_invites_code ON project_invites(join_code);
"""
