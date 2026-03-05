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
# These are showcase apps offered by the platform to users.
# config_schema doubles as metadata for the marketplace presentation.
DEFAULT_MARKETPLACE = [
    {
        "addon_id": "analytics-dashboard",
        "name": "Analytics Dashboard",
        "description": "Real-time visitor analytics and performance metrics for your deployed apps. Track page views, unique visitors, referrers, and geographic distribution.",
        "category": "analytics",
        "icon": "bar-chart",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "Understand your traffic",
            "pricing": "free",
            "highlights": ["Real-time visitors", "Geographic heatmap", "Referrer tracking", "Export CSV"],
            "featured": True,
        },
    },
    {
        "addon_id": "uptime-monitor",
        "name": "Uptime Monitor",
        "description": "24/7 HTTP health checks every 60 seconds with email and Slack alerts on downtime. Track response times and availability history.",
        "category": "monitoring",
        "icon": "heart-pulse",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "Never miss downtime",
            "pricing": "free",
            "highlights": ["60s check interval", "Email + Slack alerts", "Response time graphs", "30-day history"],
            "featured": True,
        },
    },
    {
        "addon_id": "ssl-manager",
        "name": "SSL Manager",
        "description": "Automatic Let's Encrypt certificate provisioning and renewal. Zero-config HTTPS for all your domains with wildcard support.",
        "category": "security",
        "icon": "shield",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "HTTPS everywhere",
            "pricing": "free",
            "highlights": ["Auto-renewal", "Wildcard certs", "Zero config", "Let's Encrypt"],
            "featured": False,
        },
    },
    {
        "addon_id": "database-viewer",
        "name": "Database Viewer",
        "description": "Browse and query SQLite and Postgres databases directly from the dashboard. Visual table explorer, SQL editor, and export tools.",
        "category": "tools",
        "icon": "table",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "Explore your data",
            "pricing": "free",
            "highlights": ["Visual table browser", "SQL editor", "Export to CSV/JSON", "Query history"],
            "featured": False,
        },
    },
    {
        "addon_id": "email-service",
        "name": "Email Service",
        "description": "Transactional email sending with templates, delivery tracking, and bounce handling. Send from your own domain.",
        "category": "messaging",
        "icon": "mail",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "Reliable email delivery",
            "pricing": "free",
            "highlights": ["Custom templates", "Delivery tracking", "Bounce handling", "Domain verification"],
            "featured": False,
        },
    },
    {
        "addon_id": "scheduled-tasks",
        "name": "Scheduled Tasks",
        "description": "Visual cron job manager with retry logic, execution logs, and failure notifications. No more editing crontabs manually.",
        "category": "automation",
        "icon": "timer",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "Automate everything",
            "pricing": "free",
            "highlights": ["Visual scheduler", "Retry logic", "Execution logs", "Failure alerts"],
            "featured": False,
        },
    },
]
