"""MMS Config - Settings loaded from environment variables."""
import os
from pathlib import Path

# Root of the mms project (where this repo lives)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings:
    # Paths
    DATA_DIR = Path(os.environ.get("MMS_DATA_DIR", "/opt/mms/data"))
    DB_PATH = DATA_DIR / "mms.db"
    KEYS_DIR = DATA_DIR / "keys"
    CONFIG_DIR = Path(os.environ.get("MMS_CONFIG_DIR", "/opt/mms/config"))
    TOKEN_PATH = CONFIG_DIR / "token"

    # Workspaces live in the repo under workspaces/
    WORKSPACES_DIR = Path(os.environ.get("MMS_WORKSPACES_DIR", str(_PROJECT_ROOT / "workspaces")))

    # Dev fallbacks
    DEV_DATA_DIR = Path("/tmp/mms/data")
    DEV_DB_PATH = DEV_DATA_DIR / "mms.db"

    # Vultr
    VULTR_API_KEY = os.environ.get("VULTR_API_KEY", "")
    VULTR_BASE_URL = "https://api.vultr.com/v2"
    VULTR_DEFAULT_REGION = os.environ.get("VULTR_DEFAULT_REGION", "ewr")
    VULTR_DEFAULT_PLAN = os.environ.get("VULTR_DEFAULT_PLAN", "vc2-1c-1gb")
    VULTR_DEFAULT_OS = int(os.environ.get("VULTR_DEFAULT_OS", "2284"))  # Ubuntu 24.04

    # Cloudflare (optional — user provides per-project or global)
    CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")

    # Server
    HOST = os.environ.get("MMS_HOST", "0.0.0.0")
    PORT = int(os.environ.get("MMS_PORT", "8000"))
    CORS_ORIGINS = os.environ.get(
        "MMS_CORS_ORIGINS",
        "https://zarnetti.com,http://localhost:3000,http://localhost:8000"
    ).split(",")

    # Metrics service
    METRICS_URL = os.environ.get("MMS_METRICS_URL", "http://127.0.0.1:8081")

    # Admin
    ADMIN_EMAIL = os.environ.get("MMS_ADMIN_EMAIL", "ayman_gha@hotmail.com")

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
        """Get the path for a workspace: workspaces/{name}."""
        p = cls.WORKSPACES_DIR / name
        return p

    @classmethod
    def workspace_dir(cls, project_id: str, name: str) -> Path:
        """Legacy: project-scoped workspace dir. Now uses flat workspaces/."""
        return cls.workspace_path(name)

    @classmethod
    def keys_dir(cls, project_id: str) -> Path:
        base = cls.DATA_DIR if cls.DATA_DIR.parent.exists() else cls.DEV_DATA_DIR
        p = base / "keys" / project_id
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
