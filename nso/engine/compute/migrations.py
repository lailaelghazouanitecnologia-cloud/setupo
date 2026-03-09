TABLES = """
    CREATE TABLE IF NOT EXISTS instances (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        type TEXT DEFAULT 'setup',
        provider TEXT DEFAULT 'vultr',
        provider_id TEXT DEFAULT '',
        label TEXT DEFAULT '',
        region TEXT DEFAULT 'ewr',
        plan TEXT DEFAULT 'vc2-1c-1gb',
        os_id INTEGER DEFAULT 2284,
        ip TEXT,
        domain TEXT,
        state TEXT DEFAULT 'creating',
        ssh_key_id TEXT,
        workspace TEXT,
        error TEXT,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        ready_at TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS instance_metrics (
        id TEXT PRIMARY KEY,
        instance_id TEXT NOT NULL UNIQUE,
        ip TEXT DEFAULT '',
        reachable INTEGER DEFAULT 0,
        cpu_percent REAL DEFAULT 0,
        mem_percent REAL DEFAULT 0,
        mem_used_mb INTEGER DEFAULT 0,
        mem_total_mb INTEGER DEFAULT 0,
        disk_percent REAL DEFAULT 0,
        disk_used_gb REAL DEFAULT 0,
        disk_total_gb REAL DEFAULT 0,
        load_1m REAL DEFAULT 0,
        uptime INTEGER DEFAULT 0,
        history TEXT DEFAULT '[]',
        collected_at TEXT DEFAULT '',
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS instance_services (
        id TEXT PRIMARY KEY,
        instance_id TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        pid INTEGER DEFAULT 0,
        port INTEGER DEFAULT 0,
        version TEXT DEFAULT '',
        command TEXT DEFAULT '',
        working_dir TEXT DEFAULT '/opt/app',
        health_path TEXT DEFAULT '',
        restart_policy TEXT DEFAULT 'always',
        restart_count INTEGER DEFAULT 0,
        cpu_percent REAL DEFAULT 0,
        rss_mb REAL DEFAULT 0,
        uptime INTEGER DEFAULT 0,
        consecutive_failures INTEGER DEFAULT 0,
        error TEXT DEFAULT '',
        depends_on TEXT DEFAULT '[]',
        collected_at TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (instance_id) REFERENCES instances(id) ON DELETE CASCADE,
        UNIQUE(instance_id, name)
    );
"""

TABLES += """
    CREATE TABLE IF NOT EXISTS compute_nodes (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,

        -- Identity
        label TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'vultr',
        instance_id TEXT DEFAULT NULL,

        -- Connection
        ip TEXT DEFAULT '',
        agent_port INTEGER DEFAULT 8081,
        agent_reachable INTEGER DEFAULT 0,
        tunnel_config TEXT DEFAULT '{}',

        -- State
        status TEXT DEFAULT 'pending',
        role TEXT DEFAULT 'general',

        -- Resources: total capacity
        cpu_cores REAL DEFAULT 1,
        mem_total_mb INTEGER DEFAULT 1024,
        disk_total_gb REAL DEFAULT 25,

        -- Resources: allocated (sum of service cpu/mem requests)
        cpu_allocated REAL DEFAULT 0,
        mem_allocated_mb INTEGER DEFAULT 0,

        -- Resources: real-time metrics from agent
        cpu_used_percent REAL DEFAULT 0,
        mem_used_percent REAL DEFAULT 0,
        disk_used_percent REAL DEFAULT 0,
        load_1m REAL DEFAULT 0,

        -- Placement control
        reserved_for TEXT DEFAULT NULL,
        max_services INTEGER DEFAULT 50,
        buffer_cpu_percent REAL DEFAULT 10,
        buffer_mem_percent REAL DEFAULT 10,

        -- Classification
        tags TEXT DEFAULT '[]',
        capabilities TEXT DEFAULT '[]',
        labels TEXT DEFAULT '{}',

        -- Metadata
        os_info TEXT DEFAULT '{}',
        agent_version TEXT DEFAULT '',
        last_heartbeat TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );
"""

async def run_alterations(conn, logger):
    """Fix FK constraints on existing tables (SQLite requires table recreation)."""

    # ── Fix compute_vms: add ON DELETE CASCADE to both FKs ──
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='compute_vms'"
    )
    if await cursor.fetchone():
        # Check if already fixed by looking at the SQL
        cursor = await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='compute_vms'"
        )
        row = await cursor.fetchone()
        if row and "ON DELETE CASCADE" not in (row[0] or "").upper():
            logger.info("Migrating compute_vms: adding ON DELETE CASCADE")
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS compute_vms_new (
                    id TEXT PRIMARY KEY,
                    host_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    instance_id TEXT DEFAULT '',
                    plan_id TEXT DEFAULT '',
                    label TEXT DEFAULT '',
                    status TEXT DEFAULT 'creating',
                    vcpus INTEGER DEFAULT 1,
                    ram_mb INTEGER DEFAULT 512,
                    disk_gb INTEGER DEFAULT 10,
                    bandwidth_gb INTEGER DEFAULT 100,
                    ip_internal TEXT DEFAULT '',
                    ip_external TEXT DEFAULT '',
                    port_start INTEGER DEFAULT 0,
                    port_end INTEGER DEFAULT 0,
                    container_id TEXT DEFAULT '',
                    pid INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now')),
                    started_at TEXT,
                    stopped_at TEXT,
                    FOREIGN KEY (host_id) REFERENCES compute_hosts(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                INSERT OR IGNORE INTO compute_vms_new SELECT * FROM compute_vms;
                DROP TABLE compute_vms;
                ALTER TABLE compute_vms_new RENAME TO compute_vms;
                CREATE INDEX IF NOT EXISTS idx_compute_vms_host ON compute_vms(host_id);
                CREATE INDEX IF NOT EXISTS idx_compute_vms_project ON compute_vms(project_id);
                CREATE INDEX IF NOT EXISTS idx_compute_vms_status ON compute_vms(status);
            """)
            logger.info("compute_vms FK migration complete")


INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_instances_project ON instances(project_id);
    CREATE INDEX IF NOT EXISTS idx_instances_state ON instances(state);
    CREATE INDEX IF NOT EXISTS idx_instances_project_state ON instances(project_id, state);
    CREATE INDEX IF NOT EXISTS idx_instance_metrics_instance ON instance_metrics(instance_id);
    CREATE INDEX IF NOT EXISTS idx_instance_services_instance ON instance_services(instance_id);
    CREATE INDEX IF NOT EXISTS idx_instance_services_status ON instance_services(status);
    CREATE INDEX IF NOT EXISTS idx_compute_nodes_project ON compute_nodes(project_id);
    CREATE INDEX IF NOT EXISTS idx_compute_nodes_status ON compute_nodes(status);
    CREATE INDEX IF NOT EXISTS idx_compute_nodes_role ON compute_nodes(role);
    CREATE INDEX IF NOT EXISTS idx_compute_nodes_reserved ON compute_nodes(reserved_for);
    CREATE INDEX IF NOT EXISTS idx_compute_nodes_instance ON compute_nodes(instance_id);
"""
