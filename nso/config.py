import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings:
    DATA_DIR = Path(os.environ.get("NSO_DATA_DIR", "/opt/nso/data"))
    DB_PATH = DATA_DIR / "nso.db"
    KEYS_DIR = DATA_DIR / "keys"
    CONFIG_DIR = Path(os.environ.get("NSO_CONFIG_DIR", "/opt/nso/config"))
    TOKEN_PATH = CONFIG_DIR / "token"
    WORKSPACES_DIR = Path(os.environ.get("NSO_WORKSPACES_DIR", "/opt/nso/workspaces"))

    DEV_DATA_DIR = Path("/tmp/nso/data")
    DEV_DB_PATH = DEV_DATA_DIR / "nso.db"

    VULTR_API_KEY = os.environ.get("VULTR_API_KEY", "")
    VULTR_BASE_URL = "https://api.vultr.com/v2"
    VULTR_DEFAULT_REGION = os.environ.get("VULTR_DEFAULT_REGION", "ewr")
    VULTR_DEFAULT_PLAN = os.environ.get("VULTR_DEFAULT_PLAN", "vc2-1c-1gb")
    try:
        VULTR_DEFAULT_OS = int(os.environ.get("VULTR_DEFAULT_OS", "2136"))
    except ValueError:
        VULTR_DEFAULT_OS = 2136

    CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")
    CF_NSO_ZONE_ID = os.environ.get("CF_NSO_ZONE_ID", "")
    NSO_BASE_DOMAIN = os.environ.get("NSO_BASE_DOMAIN", "nso.dev")

    R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET = os.environ.get("R2_BUCKET", "nso")
    R2_READY_BUCKET = os.environ.get("R2_READY_BUCKET", "nso-ready")
    R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

    HOST = os.environ.get("NSO_HOST", "0.0.0.0")
    try:
        PORT = int(os.environ.get("NSO_PORT", "8000"))
    except ValueError:
        PORT = 8000
    SERVER_MODE = os.environ.get("NSO_SERVER_MODE", "full")  # "admin", "user", "full"
    ADMIN_ALLOWED_IPS = [ip.strip() for ip in os.environ.get("NSO_ADMIN_ALLOWED_IPS", "").split(",") if ip.strip()]
    ADMIN_SECRET = os.environ.get("NSO_ADMIN_SECRET", "")
    ADMIN_HOSTS = [h.strip() for h in os.environ.get("NSO_ADMIN_HOSTS", "sonfazt.nso.dev,localhost,127.0.0.1").split(",") if h.strip()]
    CORS_ORIGINS = [o.strip() for o in os.environ.get(
        "NSO_CORS_ORIGINS",
        "https://nso.dev,https://sonfazt.nso.dev,http://localhost:3000,http://localhost:3001,http://localhost:8000"
    ).split(",") if o.strip()]

    ADMIN_EMAIL = os.environ.get("NSO_ADMIN_EMAIL", "admin@nso.dev")
    ADMIN_PASSWORD = os.environ.get("NSO_ADMIN_PASSWORD", "")
    AGENT_ADMIN_PASSWORD = os.environ.get("AGENT_ADMIN_PASSWORD", "")

    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

    # Build server (optional — builds run on user's agent if not configured)
    BUILD_SERVER_URL = os.environ.get("NSO_BUILD_SERVER_URL", "")
    BUILD_SERVER_TOKEN = os.environ.get("NSO_BUILD_SERVER_TOKEN", "")

    # Deploy agent LLM (any OpenAI-compatible API: Groq, OpenRouter, etc.)
    DEPLOY_AGENT_API_KEY = os.environ.get("DEPLOY_AGENT_API_KEY", "")
    DEPLOY_AGENT_API_URL = os.environ.get("DEPLOY_AGENT_API_URL", "https://api.groq.com/openai/v1")
    DEPLOY_AGENT_MODEL = os.environ.get("DEPLOY_AGENT_MODEL", "openai/gpt-oss-20b")

    # Mesh
    MESH_KEYS_DIR = DATA_DIR / "mesh"
    MESH_HEALTH_INTERVAL = int(os.environ.get("NSO_MESH_HEALTH_INTERVAL", "30"))

    SERVE_STATIC = bool(os.environ.get("NSO_SERVE_STATIC", ""))

    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    try:
        SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        SMTP_PORT = 587
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "nso@nso.dev")

    @classmethod
    def db_path(cls) -> Path:
        if cls.DATA_DIR.parent.exists():
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
            return cls.DB_PATH
        cls.DEV_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return cls.DEV_DB_PATH

    @classmethod
    def project_dir(cls, project_id: str) -> Path:
        base = cls.DATA_DIR if cls.DATA_DIR.parent.exists() else cls.DEV_DATA_DIR
        p = base / "projects" / project_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def workspace_path(cls, name: str) -> Path:
        return cls.WORKSPACES_DIR / name

    @classmethod
    def keys_dir(cls, project_id: str) -> Path:
        base = cls.DATA_DIR if cls.DATA_DIR.parent.exists() else cls.DEV_DATA_DIR
        p = base / "keys" / project_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def r2_config(cls):
        from nso.shared.models import R2Config
        return R2Config(
            bucket=cls.R2_BUCKET,
            endpoint=cls.R2_ENDPOINT,
            access_key_id=cls.R2_ACCESS_KEY_ID,
            secret_access_key=cls.R2_SECRET_ACCESS_KEY,
            public_url=cls.R2_PUBLIC_URL,
        )

    @classmethod
    def r2_ready_config(cls):
        from nso.shared.models import R2Config
        return R2Config(
            bucket=cls.R2_READY_BUCKET,
            endpoint=cls.R2_ENDPOINT,
            access_key_id=cls.R2_ACCESS_KEY_ID,
            secret_access_key=cls.R2_SECRET_ACCESS_KEY,
            public_url=cls.R2_PUBLIC_URL,
        )


settings = Settings()
