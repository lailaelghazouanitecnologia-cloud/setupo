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
"""
