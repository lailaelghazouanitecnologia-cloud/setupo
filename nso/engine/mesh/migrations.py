TABLES = """
    CREATE TABLE IF NOT EXISTS mesh_devices (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        host TEXT NOT NULL,
        ssh_port INTEGER DEFAULT 22,
        ssh_user TEXT DEFAULT 'root',
        status TEXT DEFAULT 'pending',
        install_token TEXT,
        ssh_fingerprint TEXT,
        os_info TEXT DEFAULT '{}',
        agent_version TEXT DEFAULT '',
        last_seen_at TEXT,
        tags TEXT DEFAULT '[]',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, name)
    );

    CREATE TABLE IF NOT EXISTS mesh_groups (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, name)
    );

    CREATE TABLE IF NOT EXISTS mesh_device_groups (
        device_id TEXT NOT NULL,
        group_id TEXT NOT NULL,
        PRIMARY KEY (device_id, group_id),
        FOREIGN KEY (device_id) REFERENCES mesh_devices(id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES mesh_groups(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS mesh_operations (
        id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        command TEXT DEFAULT '',
        exit_code INTEGER,
        stdout TEXT DEFAULT '',
        stderr TEXT DEFAULT '',
        duration_ms INTEGER DEFAULT 0,
        triggered_by TEXT DEFAULT 'system',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (device_id) REFERENCES mesh_devices(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_mesh_devices_project ON mesh_devices(project_id);
    CREATE INDEX IF NOT EXISTS idx_mesh_devices_status ON mesh_devices(status);
    CREATE INDEX IF NOT EXISTS idx_mesh_groups_project ON mesh_groups(project_id);
    CREATE INDEX IF NOT EXISTS idx_mesh_device_groups_device ON mesh_device_groups(device_id);
    CREATE INDEX IF NOT EXISTS idx_mesh_device_groups_group ON mesh_device_groups(group_id);
    CREATE INDEX IF NOT EXISTS idx_mesh_operations_device ON mesh_operations(device_id);
    CREATE INDEX IF NOT EXISTS idx_mesh_operations_created ON mesh_operations(created_at);
"""
