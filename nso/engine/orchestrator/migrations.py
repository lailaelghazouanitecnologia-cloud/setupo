TABLES = """
    CREATE TABLE IF NOT EXISTS instance_pool (
        id TEXT PRIMARY KEY,
        instance_id TEXT NOT NULL UNIQUE,
        label TEXT DEFAULT '',
        role TEXT DEFAULT 'hybrid',
        status TEXT DEFAULT 'active',
        ip TEXT,
        region TEXT DEFAULT 'ewr',
        plan TEXT DEFAULT 'vc2-1c-1gb',
        max_concurrent_builds INTEGER DEFAULT 2,
        cpu_percent REAL DEFAULT 0.0,
        mem_percent REAL DEFAULT 0.0,
        disk_percent REAL DEFAULT 0.0,
        active_builds INTEGER DEFAULT 0,
        last_heartbeat TEXT,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS build_queue (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace TEXT NOT NULL,
        branch TEXT DEFAULT 'main',
        assigned_node_id TEXT,
        status TEXT DEFAULT 'queued',
        priority INTEGER DEFAULT 0,
        build_command TEXT DEFAULT 'npm run build',
        logs TEXT DEFAULT '',
        error TEXT,
        metadata TEXT DEFAULT '{}',
        queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
        started_at TEXT,
        finished_at TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_node_id) REFERENCES instance_pool(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS orchestrator_alerts (
        id TEXT PRIMARY KEY,
        node_id TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        severity TEXT DEFAULT 'warning',
        message TEXT DEFAULT '',
        value REAL DEFAULT 0.0,
        threshold REAL DEFAULT 0.0,
        resolved INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        FOREIGN KEY (node_id) REFERENCES instance_pool(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS lb_pools (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        project_id TEXT NOT NULL DEFAULT '',
        algorithm TEXT DEFAULT 'round_robin',
        health_check_path TEXT DEFAULT '/api/health',
        health_check_interval INTEGER DEFAULT 30,
        health_check_timeout INTEGER DEFAULT 5,
        max_fails INTEGER DEFAULT 3,
        sticky_sessions INTEGER DEFAULT 0,
        sticky_cookie TEXT DEFAULT 'NSO_LB_SID',
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS lb_backends (
        id TEXT PRIMARY KEY,
        pool_id TEXT NOT NULL,
        instance_id TEXT NOT NULL,
        ip TEXT NOT NULL,
        port INTEGER DEFAULT 8000,
        weight INTEGER DEFAULT 1,
        status TEXT DEFAULT 'healthy',
        active_connections INTEGER DEFAULT 0,
        total_requests INTEGER DEFAULT 0,
        failed_health_checks INTEGER DEFAULT 0,
        last_health_check TEXT,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pool_id) REFERENCES lb_pools(id) ON DELETE CASCADE,
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS lb_rules (
        id TEXT PRIMARY KEY,
        pool_id TEXT NOT NULL,
        match_type TEXT DEFAULT 'prefix',
        match_value TEXT DEFAULT '/',
        priority INTEGER DEFAULT 0,
        headers TEXT DEFAULT '{}',
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pool_id) REFERENCES lb_pools(id) ON DELETE CASCADE
    );
"""

async def run_alterations(conn, logger):
    """No-op for PostgreSQL — FKs are set correctly in initial DDL."""
    pass


INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_pool_instance ON instance_pool(instance_id);
    CREATE INDEX IF NOT EXISTS idx_pool_role ON instance_pool(role);
    CREATE INDEX IF NOT EXISTS idx_pool_status ON instance_pool(status);
    CREATE INDEX IF NOT EXISTS idx_build_queue_status ON build_queue(status);
    CREATE INDEX IF NOT EXISTS idx_build_queue_project ON build_queue(project_id);
    CREATE INDEX IF NOT EXISTS idx_build_queue_node ON build_queue(assigned_node_id);
    CREATE INDEX IF NOT EXISTS idx_build_queue_queued ON build_queue(queued_at);
    CREATE INDEX IF NOT EXISTS idx_orch_alerts_node ON orchestrator_alerts(node_id);
    CREATE INDEX IF NOT EXISTS idx_orch_alerts_resolved ON orchestrator_alerts(resolved);
    CREATE INDEX IF NOT EXISTS idx_lb_pools_active ON lb_pools(active);
    CREATE INDEX IF NOT EXISTS idx_lb_pools_project ON lb_pools(project_id);
    CREATE INDEX IF NOT EXISTS idx_lb_backends_pool ON lb_backends(pool_id);
    CREATE INDEX IF NOT EXISTS idx_lb_backends_status ON lb_backends(status);
    CREATE INDEX IF NOT EXISTS idx_lb_backends_instance ON lb_backends(instance_id);
    CREATE INDEX IF NOT EXISTS idx_lb_rules_pool ON lb_rules(pool_id);
    CREATE INDEX IF NOT EXISTS idx_lb_rules_priority ON lb_rules(priority);
"""
