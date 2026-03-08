"""
Shared secrets classification — single source of truth for bucket rules.

Used by:
  - nso/engine/workspace/secrets_routes.py (API bucket assignment)
  - nso/engine/deploy_agent/tools.py (agent secret management)
  - nso/engine/addons/routes_addons/catalog.py (connector sync)
"""

# ── Bucket definitions ──

BUCKETS = [
    {"name": "auth", "label": "Authentication", "prefixes": [
        "NSO_ADMIN", "AGENT_ADMIN", "JWT_", "SECRET_", "NSO_JWT_",
    ]},
    {"name": "providers", "label": "Providers", "prefixes": [
        "VULTR_", "CF_",
    ]},
    {"name": "storage", "label": "Storage (R2)", "prefixes": [
        "R2_",
    ]},
    {"name": "connectors", "label": "Connectors", "prefixes": [
        "GITHUB_", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_BUCKET",
        "SLACK_BOT_TOKEN", "SLACK_WEBHOOK_URL",
        "CF_CONNECTOR_", "R2_CONNECTOR_",
    ]},
    {"name": "system", "label": "System", "prefixes": [
        "NSO_HOST", "NSO_PORT", "NSO_DATA_", "NSO_CONFIG_", "NSO_WORKSPACES_",
        "NSO_CORS_", "NSO_BASE_", "NSO_AGENT_", "NSO_SERVE",
        "HOST", "PORT", "DB_", "LOG_", "CORS_",
    ]},
]

BUCKET_NAMES = [b["name"] for b in BUCKETS] + ["custom"]


def classify_secret(key: str) -> str:
    """Classify a secret key into a bucket based on prefix rules."""
    for bucket in BUCKETS:
        if any(key.startswith(p) for p in bucket["prefixes"]):
            return bucket["name"]
    return "custom"


# ── Connector → secret key mapping ──

CONNECTOR_SECRET_MAP = {
    "github": {"token": "GITHUB_TOKEN"},
    "s3": {
        "endpoint": "S3_ENDPOINT",
        "access_key": "S3_ACCESS_KEY",
        "secret_key": "S3_SECRET_KEY",
        "bucket": "S3_BUCKET",
    },
    "slack": {
        "bot_token": "SLACK_BOT_TOKEN",
        "webhook_url": "SLACK_WEBHOOK_URL",
    },
    "cloudflare": {
        "api_token": "CF_CONNECTOR_API_TOKEN",
        "api_key": "CF_CONNECTOR_API_KEY",
        "email": "CF_CONNECTOR_EMAIL",
    },
    "r2": {
        "endpoint": "R2_CONNECTOR_ENDPOINT",
        "access_key": "R2_CONNECTOR_ACCESS_KEY",
        "secret_key": "R2_CONNECTOR_SECRET_KEY",
        "bucket": "R2_CONNECTOR_BUCKET",
    },
}
