"""Base addon types and shared logic."""

ADDON_TYPES = ("connector", "plugin", "marketplace")

# Default connectors — external service integrations
DEFAULT_CONNECTORS = [
    {
        "addon_id": "github",
        "name": "GitHub",
        "description": "Connect repositories, trigger deploys on push, and sync issues.",
        "category": "vcs",
        "icon": "github",
        "addon_type": "connector",
    },
    {
        "addon_id": "supabase",
        "name": "Supabase",
        "description": "Managed Postgres database, auth, and realtime subscriptions.",
        "category": "database",
        "icon": "database",
        "addon_type": "connector",
    },
    {
        "addon_id": "s3",
        "name": "Amazon S3",
        "description": "External S3-compatible object storage for files and assets.",
        "category": "storage",
        "icon": "cloud",
        "addon_type": "connector",
    },
    {
        "addon_id": "slack",
        "name": "Slack",
        "description": "Deploy notifications, alerts, and status updates to Slack channels.",
        "category": "messaging",
        "icon": "message-square",
        "addon_type": "connector",
    },
    {
        "addon_id": "docker-registry",
        "name": "Docker Registry",
        "description": "Pull and deploy container images from Docker Hub or private registries.",
        "category": "containers",
        "icon": "container",
        "addon_type": "connector",
    },
]

# Default plugins — feature extensions (migrated from old plugin system)
DEFAULT_PLUGINS = [
    {
        "addon_id": "storage",
        "name": "Cloud Storage",
        "description": "S3-compatible object storage powered by Cloudflare R2. Upload, manage, and serve files.",
        "category": "storage",
        "icon": "hard-drive",
        "addon_type": "plugin",
        "config_schema": {
            "max_size_mb": {"type": "number", "default": 500, "label": "Max storage (MB)"},
        },
    },
    {
        "addon_id": "monitoring",
        "name": "Monitoring",
        "description": "System metrics, alerts, and uptime tracking for your instances.",
        "category": "observability",
        "icon": "activity",
        "addon_type": "plugin",
    },
    {
        "addon_id": "backups",
        "name": "Backups",
        "description": "Automated snapshot and restore for workspaces and deployments.",
        "category": "data",
        "icon": "archive",
        "addon_type": "plugin",
    },
    {
        "addon_id": "logs",
        "name": "Log Viewer",
        "description": "Centralized log aggregation and real-time search across instances.",
        "category": "observability",
        "icon": "file-text",
        "addon_type": "plugin",
    },
    {
        "addon_id": "dns",
        "name": "DNS Manager",
        "description": "Manage DNS records and routing for your domains via Cloudflare.",
        "category": "networking",
        "icon": "globe",
        "addon_type": "plugin",
    },
    {
        "addon_id": "cron",
        "name": "Cron Jobs",
        "description": "Schedule and manage recurring tasks on your instances.",
        "category": "automation",
        "icon": "clock",
        "addon_type": "plugin",
    },
]

# Default marketplace apps — admin-curated applications
DEFAULT_MARKETPLACE = [
    {
        "addon_id": "analytics-dashboard",
        "name": "Analytics Dashboard",
        "description": "Real-time visitor analytics and performance metrics for your deployed apps.",
        "category": "analytics",
        "icon": "bar-chart",
        "addon_type": "marketplace",
        "author": "nso",
    },
    {
        "addon_id": "uptime-monitor",
        "name": "Uptime Monitor",
        "description": "24/7 HTTP health checks with email and Slack alerts on downtime.",
        "category": "monitoring",
        "icon": "heart-pulse",
        "addon_type": "marketplace",
        "author": "nso",
    },
    {
        "addon_id": "ssl-manager",
        "name": "SSL Manager",
        "description": "Automatic Let's Encrypt certificate provisioning and renewal.",
        "category": "security",
        "icon": "shield",
        "addon_type": "marketplace",
        "author": "nso",
    },
    {
        "addon_id": "database-viewer",
        "name": "Database Viewer",
        "description": "Browse and query SQLite and Postgres databases directly from the dashboard.",
        "category": "tools",
        "icon": "table",
        "addon_type": "marketplace",
        "author": "nso",
    },
]
