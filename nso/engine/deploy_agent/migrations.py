TABLES = """
    CREATE TABLE IF NOT EXISTS deploy_threads (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        user_id TEXT DEFAULT '',
        workspace TEXT DEFAULT '',
        title TEXT DEFAULT 'New deploy',
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS deploy_messages (
        id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT DEFAULT '',
        tool_calls TEXT DEFAULT '[]',
        tool_results TEXT DEFAULT '[]',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (thread_id) REFERENCES deploy_threads(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_deploy_threads_project ON deploy_threads(project_id);
    CREATE INDEX IF NOT EXISTS idx_deploy_threads_user ON deploy_threads(user_id);
    CREATE INDEX IF NOT EXISTS idx_deploy_messages_thread ON deploy_messages(thread_id);
"""
