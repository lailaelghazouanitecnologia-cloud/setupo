"""Symmetric encryption for secrets at rest (Fernet)."""

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet

from nso.config import settings

logger = logging.getLogger("nso.shared.crypto")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = settings.ENCRYPTION_KEY
    if not key:
        # Derive a stable key from JWT_SECRET or generate one
        jwt_secret = os.environ.get("NSO_JWT_SECRET", "")
        if jwt_secret:
            # Derive a Fernet-compatible key from the JWT secret
            derived = hashlib.sha256(jwt_secret.encode()).digest()
            key = base64.urlsafe_b64encode(derived).decode()
        else:
            logger.warning("NSO_ENCRYPTION_KEY not set — generating ephemeral key (passwords won't survive restart)")
            key = Fernet.generate_key().decode()

    # Ensure the key is valid Fernet format (32 url-safe base64 bytes)
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        # Key isn't valid Fernet — derive one from it
        derived = hashlib.sha256(key.encode()).digest()
        _fernet = Fernet(base64.urlsafe_b64encode(derived))

    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returns base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to string."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
