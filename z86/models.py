from pydantic import BaseModel


class AccessKey(BaseModel):
    access_key_id: str      # z86_ak_xxxx
    secret_access_key: str  # z86_sk_xxxx
    owner_id: str           # user_id or project_id
    owner_type: str         # "user" | "project"
    label: str = ""
    active: bool = True
    allowed_buckets: list[str] = []  # empty = all buckets owned


class BucketInfo(BaseModel):
    name: str
    owner_id: str
    created_at: str
    object_count: int = 0
    total_size: int = 0
    region: str = "local"


class ObjectMeta(BaseModel):
    key: str
    bucket: str
    size: int
    content_type: str = "application/octet-stream"
    sha256: str
    created_at: str
    updated_at: str


class CreateKeyRequest(BaseModel):
    owner_id: str
    owner_type: str = "project"
    label: str = ""
    allowed_buckets: list[str] = []


class CreateBucketRequest(BaseModel):
    name: str
    owner_id: str


class StorageStats(BaseModel):
    total_buckets: int = 0
    total_objects: int = 0
    total_size_bytes: int = 0
    total_keys: int = 0
