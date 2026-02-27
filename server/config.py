import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings:
    DATA_DIR = Path(os.environ.get("SETUPO_DATA_DIR", "/opt/setupo/data"))
    DB_PATH = DATA_DIR / "setupo.db"
    KEYS_DIR = DATA_DIR / "keys"
    CONFIG_DIR = Path(os.environ.get("SETUPO_CONFIG_DIR", "/opt/setupo/config"))
    TOKEN_PATH = CONFIG_DIR / "token"
    WORKSPACES_DIR = Path(os.environ.get("SETUPO_WORKSPACES_DIR", "/opt/setupo/workspaces"))

    DEV_DATA_DIR = Path("/tmp/setupo/data")
    DEV_DB_PATH = DEV_DATA_DIR / "setupo.db"

    VULTR_API_KEY = os.environ.get("VULTR_API_KEY", "")
    VULTR_BASE_URL = "https://api.vultr.com/v2"
    VULTR_DEFAULT_REGION = os.environ.get("VULTR_DEFAULT_REGION", "ewr")
    VULTR_DEFAULT_PLAN = os.environ.get("VULTR_DEFAULT_PLAN", "vc2-1c-1gb")
    VULTR_DEFAULT_OS = int(os.environ.get("VULTR_DEFAULT_OS", "2136"))

    CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")

    R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET = os.environ.get("R2_BUCKET", "nso")
    R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

    HOST = os.environ.get("SETUPO_HOST", "0.0.0.0")
    PORT = int(os.environ.get("SETUPO_PORT", "8000"))
    CORS_ORIGINS = os.environ.get(
        "SETUPO_CORS_ORIGINS",
        "https://nso.dev,http://localhost:3000,http://localhost:8000"
    ).split(",")

    ADMIN_EMAIL = os.environ.get("SETUPO_ADMIN_EMAIL", "admin@setupo.dev")
    ADMIN_PASSWORD = os.environ.get("SETUPO_ADMIN_PASSWORD", "")
    AGENT_ADMIN_PASSWORD = os.environ.get("AGENT_ADMIN_PASSWORD", "")

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
    def workspace_dir(cls, project_id: str, name: str) -> Path:
        return cls.workspace_path(name)

    @classmethod
    def keys_dir(cls, project_id: str) -> Path:
        base = cls.DATA_DIR if cls.DATA_DIR.parent.exists() else cls.DEV_DATA_DIR
        p = base / "keys" / project_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def r2_config(cls):
        from core.models import R2Config
        return R2Config(
            bucket=cls.R2_BUCKET,
            endpoint=cls.R2_ENDPOINT,
            access_key_id=cls.R2_ACCESS_KEY_ID,
            secret_access_key=cls.R2_SECRET_ACCESS_KEY,
            public_url=cls.R2_PUBLIC_URL,
        )


settings = Settings()
