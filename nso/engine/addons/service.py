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
        "addon_id": "cloudflare",
        "name": "Cloudflare",
        "description": "Manage DNS records, domains, and routing through your Cloudflare account.",
        "category": "dns",
        "icon": "globe",
        "addon_type": "connector",
    },
    {
        "addon_id": "r2",
        "name": "Cloudflare R2",
        "description": "S3-compatible object storage powered by Cloudflare R2. No egress fees.",
        "category": "storage",
        "icon": "database",
        "addon_type": "connector",
    },
    {
        "addon_id": "vultr",
        "name": "Vultr",
        "description": "Provision and manage cloud VPS nodes directly from Vultr.",
        "category": "compute",
        "icon": "server",
        "addon_type": "connector",
    },
    {
        "addon_id": "hetzner",
        "name": "Hetzner Cloud",
        "description": "Provision and manage Hetzner Cloud servers as compute nodes.",
        "category": "compute",
        "icon": "server",
        "addon_type": "connector",
    },
    {
        "addon_id": "runpod",
        "name": "RunPod",
        "description": "GPU machines, volumes, and serverless endpoints for ML workloads.",
        "category": "compute",
        "icon": "gpu",
        "addon_type": "connector",
    },
]

# Default plugins — feature extensions
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
        "description": "System metrics, alerts, and uptime tracking for your machines.",
        "category": "observability",
        "icon": "activity",
        "addon_type": "plugin",
    },
    {
        "addon_id": "logs",
        "name": "Log Viewer",
        "description": "Centralized log aggregation and real-time search across machines.",
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
        "description": "Schedule and manage recurring tasks on your machines.",
        "category": "automation",
        "icon": "clock",
        "addon_type": "plugin",
    },
]

# Default marketplace apps — functional apps with full backend implementation
DEFAULT_MARKETPLACE = [
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
        "description": "Automatic SSL certificate monitoring and expiration alerts. Zero-config HTTPS tracking for all your domains.",
        "category": "security",
        "icon": "shield",
        "addon_type": "marketplace",
        "author": "nso",
        "config_schema": {
            "tagline": "HTTPS everywhere",
            "pricing": "free",
            "highlights": ["Auto-check", "Expiration alerts", "Zero config", "Certificate details"],
            "featured": True,
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
            "featured": True,
        },
    },
]
