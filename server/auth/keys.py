"""API Key generation and validation."""
import hashlib
import secrets


def generate_api_key() -> str:
    """Generate a new API key: sk_live_<64 chars>."""
    return f"sk_live_{secrets.token_urlsafe(48)}"


def hash_api_key(key: str) -> str:
    """SHA256 hash of an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, key_hash: str) -> bool:
    """Verify an API key against its hash."""
    return secrets.compare_digest(hash_api_key(key), key_hash)
