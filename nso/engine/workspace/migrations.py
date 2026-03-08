TABLES = """
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        path TEXT NOT NULL,
        ws_type TEXT DEFAULT 'custom',
        stack TEXT DEFAULT '',
        description TEXT DEFAULT '',
        instance_id TEXT,
        git_url TEXT,
        branch TEXT,
        agent_visible INTEGER DEFAULT 1,
        readonly INTEGER DEFAULT 0,
        protected_files TEXT DEFAULT '[]',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS workspace_shares (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        join_code TEXT UNIQUE NOT NULL,
        permissions TEXT DEFAULT 'read',
        max_uses INTEGER DEFAULT 0,
        uses INTEGER DEFAULT 0,
        created_by TEXT NOT NULL,
        expires_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS workspace_members (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        permissions TEXT DEFAULT 'read',
        joined_via TEXT,
        joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_workspaces_project ON workspaces(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_name ON workspaces(project_id, name);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_shares_code ON workspace_shares(join_code);
    CREATE INDEX IF NOT EXISTS idx_ws_shares_workspace ON workspace_shares(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_ws_members_workspace ON workspace_members(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_ws_members_user ON workspace_members(user_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_members_unique ON workspace_members(workspace_id, user_id);
    CREATE INDEX IF NOT EXISTS idx_workspaces_instance ON workspaces(project_id, instance_id);
"""


async def run_alterations(conn, logger):
    """Add columns that may be missing from older schema versions."""
    try:
        await conn.execute("SELECT agent_visible FROM workspaces LIMIT 1")
    except Exception:
        await conn.execute("ALTER TABLE workspaces ADD COLUMN agent_visible INTEGER DEFAULT 1")
        logger.info("Added agent_visible column to workspaces")

    try:
        await conn.execute("SELECT readonly FROM workspaces LIMIT 1")
    except Exception:
        await conn.execute("ALTER TABLE workspaces ADD COLUMN readonly INTEGER DEFAULT 0")
        logger.info("Added readonly column to workspaces")

    try:
        await conn.execute("SELECT protected_files FROM workspaces LIMIT 1")
    except Exception:
        await conn.execute("ALTER TABLE workspaces ADD COLUMN protected_files TEXT DEFAULT '[]'")
        logger.info("Added protected_files column to workspaces")
