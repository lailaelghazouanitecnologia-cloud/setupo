TABLES = """
    CREATE TABLE IF NOT EXISTS plugin_catalog (
        id TEXT PRIMARY KEY,
        plugin_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        category TEXT DEFAULT '',
        icon TEXT DEFAULT '',
        author TEXT DEFAULT 'nso',
        published INTEGER DEFAULT 1,
        config_schema TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS plugins (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        plugin_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        category TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        config TEXT DEFAULT '{}',
        installed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS addon_catalog (
        id TEXT PRIMARY KEY,
        addon_id TEXT NOT NULL,
        addon_type TEXT NOT NULL DEFAULT 'plugin',
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        category TEXT DEFAULT '',
        icon TEXT DEFAULT '',
        author TEXT DEFAULT 'nso',
        published INTEGER DEFAULT 1,
        config_schema TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS addons (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        addon_id TEXT NOT NULL,
        addon_type TEXT NOT NULL DEFAULT 'plugin',
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        category TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        config TEXT DEFAULT '{}',
        installed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS modules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        display_name TEXT DEFAULT '',
        description TEXT DEFAULT '',
        version TEXT DEFAULT '1.0.0',
        category TEXT DEFAULT 'core',
        r2_key TEXT DEFAULT '',
        size INTEGER DEFAULT 0,
        hash TEXT DEFAULT '',
        published INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- GitHub webhook configs (connector: auto-deploy on push)
    CREATE TABLE IF NOT EXISTS webhook_configs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace_name TEXT NOT NULL,
        instance_id TEXT DEFAULT '',
        github_repo TEXT NOT NULL,
        github_branch TEXT DEFAULT 'main',
        secret TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        auto_deploy INTEGER DEFAULT 1,
        last_triggered TEXT DEFAULT '',
        last_status TEXT DEFAULT '',
        last_error TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        webhook_id TEXT NOT NULL,
        event TEXT DEFAULT 'push',
        github_delivery_id TEXT DEFAULT '',
        branch TEXT DEFAULT '',
        commit_sha TEXT DEFAULT '',
        commit_message TEXT DEFAULT '',
        author TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        deploy_result TEXT DEFAULT '',
        error TEXT DEFAULT '',
        received_at TEXT DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT DEFAULT '',
        FOREIGN KEY (webhook_id) REFERENCES webhook_configs(id) ON DELETE CASCADE
    );

    -- AI Apps: admin-published AI services powered by Baseten
    -- Apps are interactive pipelines with stages/templates
    CREATE TABLE IF NOT EXISTS ai_apps (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT '',
        long_description TEXT DEFAULT '',
        category TEXT DEFAULT 'general',
        icon TEXT DEFAULT 'cpu',
        cover_image TEXT DEFAULT '',
        author TEXT DEFAULT 'nso',
        published INTEGER DEFAULT 0,
        featured INTEGER DEFAULT 0,
        pricing TEXT DEFAULT 'free',
        credits_per_run INTEGER DEFAULT 0,
        baseten_model_id TEXT DEFAULT '',
        baseten_api_url TEXT DEFAULT '',
        baseten_api_key TEXT DEFAULT '',
        input_schema TEXT DEFAULT '{}',
        output_schema TEXT DEFAULT '{}',
        example_input TEXT DEFAULT '{}',
        example_output TEXT DEFAULT '{}',
        system_prompt TEXT DEFAULT '',
        max_timeout_seconds INTEGER DEFAULT 60,
        total_runs INTEGER DEFAULT 0,
        pipeline_stages TEXT DEFAULT '[]',
        templates TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- AI App sessions: ongoing multi-step interactions with an app
    CREATE TABLE IF NOT EXISTS ai_app_sessions (
        id TEXT PRIMARY KEY,
        app_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        user_id TEXT DEFAULT '',
        thread_id TEXT DEFAULT '',
        current_stage TEXT DEFAULT '',
        stage_data TEXT DEFAULT '{}',
        collected_data TEXT DEFAULT '{}',
        status TEXT DEFAULT 'active',
        output_folder TEXT DEFAULT 'assets',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (app_id) REFERENCES ai_apps(id) ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- AI App memory: per-project preferences + context for AI agent
    CREATE TABLE IF NOT EXISTS ai_app_memory (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        app_id TEXT NOT NULL,
        preferences TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (app_id) REFERENCES ai_apps(id) ON DELETE CASCADE
    );

    -- AI App runs: execution history per project
    CREATE TABLE IF NOT EXISTS ai_app_runs (
        id TEXT PRIMARY KEY,
        app_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        user_id TEXT DEFAULT '',
        input TEXT DEFAULT '{}',
        output TEXT DEFAULT '{}',
        status TEXT DEFAULT 'pending',
        error TEXT DEFAULT '',
        latency_ms INTEGER DEFAULT 0,
        credits_charged INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT DEFAULT '',
        FOREIGN KEY (app_id) REFERENCES ai_apps(id) ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- Uptime Monitor: health check targets and results
    CREATE TABLE IF NOT EXISTS uptime_targets (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        url TEXT NOT NULL,
        label TEXT DEFAULT '',
        interval_seconds INTEGER DEFAULT 60,
        timeout_seconds INTEGER DEFAULT 10,
        expected_status INTEGER DEFAULT 200,
        enabled INTEGER DEFAULT 1,
        notify_slack INTEGER DEFAULT 0,
        notify_email INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS uptime_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id TEXT NOT NULL,
        status_code INTEGER,
        response_ms INTEGER,
        is_up INTEGER DEFAULT 1,
        error TEXT DEFAULT '',
        checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (target_id) REFERENCES uptime_targets(id) ON DELETE CASCADE
    );

    -- SSL Manager: certificate tracking
    CREATE TABLE IF NOT EXISTS ssl_certificates (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        domain TEXT NOT NULL,
        issuer TEXT DEFAULT '',
        valid_from TEXT DEFAULT '',
        valid_to TEXT DEFAULT '',
        days_remaining INTEGER DEFAULT -1,
        auto_renew INTEGER DEFAULT 1,
        last_checked TEXT DEFAULT '',
        status TEXT DEFAULT 'unknown',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    -- Scheduled Tasks: cron job definitions and execution log
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        instance_id TEXT NOT NULL,
        name TEXT NOT NULL,
        command TEXT NOT NULL,
        schedule TEXT NOT NULL,
        timezone TEXT DEFAULT 'UTC',
        enabled INTEGER DEFAULT 1,
        max_retries INTEGER DEFAULT 0,
        timeout_seconds INTEGER DEFAULT 300,
        last_run TEXT DEFAULT '',
        next_run TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS task_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        status TEXT DEFAULT 'running',
        exit_code INTEGER DEFAULT -1,
        output TEXT DEFAULT '',
        error TEXT DEFAULT '',
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT DEFAULT '',
        duration_ms INTEGER DEFAULT 0,
        FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id) ON DELETE CASCADE
    );
"""

INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_plugin_catalog_published ON plugin_catalog(published);
    CREATE INDEX IF NOT EXISTS idx_plugins_project ON plugins(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_plugins_unique ON plugins(project_id, plugin_id);
    CREATE INDEX IF NOT EXISTS idx_addon_catalog_type ON addon_catalog(addon_type);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_addon_catalog_unique ON addon_catalog(addon_id, addon_type);
    CREATE INDEX IF NOT EXISTS idx_addon_catalog_published ON addon_catalog(published);
    CREATE INDEX IF NOT EXISTS idx_addons_project ON addons(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_addons_unique ON addons(project_id, addon_id, addon_type);
    CREATE INDEX IF NOT EXISTS idx_modules_name ON modules(name);
    CREATE INDEX IF NOT EXISTS idx_modules_published ON modules(published);

    CREATE INDEX IF NOT EXISTS idx_webhook_configs_project ON webhook_configs(project_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_configs_repo ON webhook_configs(project_id, github_repo, github_branch);
    CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);

    CREATE INDEX IF NOT EXISTS idx_ai_apps_slug ON ai_apps(slug);
    CREATE INDEX IF NOT EXISTS idx_ai_apps_published ON ai_apps(published);
    CREATE INDEX IF NOT EXISTS idx_ai_apps_category ON ai_apps(category);
    CREATE INDEX IF NOT EXISTS idx_ai_app_sessions_app ON ai_app_sessions(app_id);
    CREATE INDEX IF NOT EXISTS idx_ai_app_sessions_project ON ai_app_sessions(project_id);
    CREATE INDEX IF NOT EXISTS idx_ai_app_sessions_thread ON ai_app_sessions(thread_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_app_memory_unique ON ai_app_memory(project_id, app_id);
    CREATE INDEX IF NOT EXISTS idx_ai_app_runs_app ON ai_app_runs(app_id);
    CREATE INDEX IF NOT EXISTS idx_ai_app_runs_project ON ai_app_runs(project_id);

    CREATE INDEX IF NOT EXISTS idx_uptime_targets_project ON uptime_targets(project_id);
    CREATE INDEX IF NOT EXISTS idx_uptime_results_target ON uptime_results(target_id);
    CREATE INDEX IF NOT EXISTS idx_uptime_results_checked ON uptime_results(checked_at);
    CREATE INDEX IF NOT EXISTS idx_ssl_certs_project ON ssl_certificates(project_id);
    CREATE INDEX IF NOT EXISTS idx_ssl_certs_domain ON ssl_certificates(domain);
    CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_project ON scheduled_tasks(project_id);
    CREATE INDEX IF NOT EXISTS idx_task_executions_task ON task_executions(task_id);
"""
