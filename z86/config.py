import os
from pathlib import Path


class Z86Settings:
    HOST = os.environ.get("Z86_HOST", "0.0.0.0")
    PORT = int(os.environ.get("Z86_PORT", "8082"))

    # Storage root — all objects stored here as files
    DATA_DIR = Path(os.environ.get("Z86_DATA_DIR", "/data/z86"))
    DB_PATH = DATA_DIR / "z86.db"

    # Admin token (shared with NSO central server)
    ADMIN_TOKEN = os.environ.get("Z86_ADMIN_TOKEN", "")

    # Max object size (default 500MB)
    MAX_OBJECT_SIZE = int(os.environ.get("Z86_MAX_OBJECT_SIZE", str(500 * 1024 * 1024)))

    # Max bucket count per access key
    MAX_BUCKETS_PER_KEY = int(os.environ.get("Z86_MAX_BUCKETS", "50"))

    # Public URL for download links
    PUBLIC_URL = os.environ.get("Z86_PUBLIC_URL", "")

    @classmethod
    def bucket_path(cls, bucket: str) -> Path:
        return cls.DATA_DIR / "buckets" / bucket

    @classmethod
    def object_path(cls, bucket: str, key: str) -> Path:
        return cls.bucket_path(bucket) / key

    @classmethod
    def meta_path(cls, bucket: str, key: str) -> Path:
        """Metadata sidecar file for an object."""
        obj = cls.object_path(bucket, key)
        return obj.parent / f".{obj.name}.z86meta"


settings = Z86Settings()
