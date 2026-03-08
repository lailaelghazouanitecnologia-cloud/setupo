TABLES = """
    CREATE TABLE IF NOT EXISTS service_registry (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace_id TEXT,
        name TEXT NOT NULL,
        version TEXT DEFAULT '',
        status TEXT DEFAULT 'inactive',
        service_type TEXT DEFAULT 'web',

        -- Resource requests & limits
        cpu_request REAL DEFAULT 0,
        cpu_limit REAL DEFAULT 0,
        mem_request_mb INTEGER DEFAULT 0,
        mem_limit_mb INTEGER DEFAULT 0,

        -- Scaling
        scaling_min INTEGER DEFAULT 1,
        scaling_max INTEGER DEFAULT 1,
        scaling_target_cpu REAL DEFAULT 0,

        -- Service spec (command, health, etc.)
        command TEXT DEFAULT '',
        port INTEGER DEFAULT 0,
        health_path TEXT DEFAULT '',
        working_dir TEXT DEFAULT '/opt/app',
        env TEXT DEFAULT '{}',
        restart_policy TEXT DEFAULT 'always',

        -- Placement
        placement_strategy TEXT DEFAULT 'shared',
        placement_node_selector TEXT DEFAULT '{}',
        placement_affinity TEXT DEFAULT '[]',
        placement_anti_affinity_services TEXT DEFAULT '[]',
        placement_anti_affinity_nodes TEXT DEFAULT '[]',
        placement_spread TEXT DEFAULT '',
        auto_provision TEXT DEFAULT '{}',

        -- Relationships
        endpoints TEXT DEFAULT '[]',
        dependencies TEXT DEFAULT '[]',
        connects_to TEXT DEFAULT '[]',

        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL,
        UNIQUE(project_id, name)
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS service_replicas (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL,
        instance_id TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        pid INTEGER DEFAULT 0,
        port INTEGER DEFAULT 0,
        version TEXT DEFAULT '',
        cpu_percent REAL DEFAULT 0,
        rss_mb REAL DEFAULT 0,
        uptime INTEGER DEFAULT 0,
        error TEXT DEFAULT '',
        collected_at TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (service_id) REFERENCES service_registry(id) ON DELETE CASCADE,
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE,
        UNIQUE(service_id, instance_id)
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS scaling_policies (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL UNIQUE,
        min_replicas INTEGER DEFAULT 1,
        max_replicas INTEGER DEFAULT 1,
        metric TEXT DEFAULT 'cpu',
        target_value REAL DEFAULT 70.0,
        cooldown_seconds INTEGER DEFAULT 300,
        scale_up_step INTEGER DEFAULT 1,
        scale_down_step INTEGER DEFAULT 1,
        last_scale_at TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (service_id) REFERENCES service_registry(id) ON DELETE CASCADE
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS service_events (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL,
        instance_id TEXT,
        event_type TEXT NOT NULL,
        message TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (service_id) REFERENCES service_registry(id) ON DELETE CASCADE
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS resource_connections (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        config TEXT DEFAULT '{}',
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, source_type, source_id, target_type, target_id)
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_service_registry_project ON service_registry(project_id);
    CREATE INDEX IF NOT EXISTS idx_service_registry_status ON service_registry(status);
    CREATE INDEX IF NOT EXISTS idx_service_registry_workspace ON service_registry(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_service_replicas_service ON service_replicas(service_id);
    CREATE INDEX IF NOT EXISTS idx_service_replicas_instance ON service_replicas(instance_id);
    CREATE INDEX IF NOT EXISTS idx_service_replicas_status ON service_replicas(status);
    CREATE INDEX IF NOT EXISTS idx_service_events_service ON service_events(service_id);
    CREATE INDEX IF NOT EXISTS idx_service_events_type ON service_events(event_type);
    CREATE INDEX IF NOT EXISTS idx_service_events_created ON service_events(created_at);
    CREATE INDEX IF NOT EXISTS idx_resource_connections_project ON resource_connections(project_id);
    CREATE INDEX IF NOT EXISTS idx_resource_connections_source ON resource_connections(source_type, source_id);
    CREATE INDEX IF NOT EXISTS idx_resource_connections_target ON resource_connections(target_type, target_id);
"""
