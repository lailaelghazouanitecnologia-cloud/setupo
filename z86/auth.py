"""
z86 authentication — AWS4-HMAC-SHA256 signature verification.

Verifies the same signature format that R2Client produces,
so existing NSO code works by just changing the endpoint.
"""
import hashlib
import hmac as hmac_mod
import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import Request, HTTPException

from z86 import db
from z86.config import settings

logger = logging.getLogger("z86.auth")


def generate_access_key() -> str:
    return f"z86_ak_{secrets.token_hex(16)}"


def generate_secret_key() -> str:
    return f"z86_sk_{secrets.token_hex(32)}"


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


async def create_access_key(
    owner_id: str,
    owner_type: str = "project",
    label: str = "",
    allowed_buckets: list[str] | None = None,
) -> dict:
    ak = generate_access_key()
    sk = generate_secret_key()
    now = datetime.now(timezone.utc).isoformat()
    key_id = f"key_{secrets.token_hex(8)}"

    await db.insert("access_keys", {
        "id": key_id,
        "access_key_id": ak,
        "secret_hash": _hash_secret(sk),
        "secret_key": sk,  # stored for signature verification
        "owner_id": owner_id,
        "owner_type": owner_type,
        "label": label,
        "active": 1,
        "allowed_buckets": "[]" if not allowed_buckets else str(allowed_buckets),
        "created_at": now,
        "updated_at": now,
    })

    logger.info("Created access key %s for %s:%s", ak, owner_type, owner_id)
    return {
        "id": key_id,
        "access_key_id": ak,
        "secret_access_key": sk,
        "owner_id": owner_id,
        "owner_type": owner_type,
        "label": label,
    }


async def get_key_by_access_id(access_key_id: str) -> dict | None:
    return await db.fetch_one("access_keys", access_key_id=access_key_id)


async def revoke_key(key_id: str):
    await db.update("access_keys", "id", key_id, {
        "active": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac_mod.new(key, msg.encode(), hashlib.sha256).digest()


def verify_aws4_signature(
    method: str,
    path: str,
    query_string: str,
    headers: dict[str, str],
    payload_hash: str,
    secret_key: str,
    auth_header: str,
) -> bool:
    """
    Verify an AWS4-HMAC-SHA256 signature.

    This implements the same algorithm as R2Client._sign() so that
    requests signed by the existing client are accepted.
    """
    try:
        # Parse Authorization header
        # Format: AWS4-HMAC-SHA256 Credential=ak/date/region/s3/aws4_request, SignedHeaders=..., Signature=...
        parts = auth_header.replace("AWS4-HMAC-SHA256 ", "").split(", ")
        auth_parts = {}
        for p in parts:
            k, v = p.split("=", 1)
            auth_parts[k] = v

        credential = auth_parts["Credential"]
        signed_headers_str = auth_parts["SignedHeaders"]
        provided_signature = auth_parts["Signature"]

        # Extract credential scope
        cred_parts = credential.split("/")
        access_key = cred_parts[0]
        date_stamp = cred_parts[1]
        region = cred_parts[2]
        service = cred_parts[3]
        credential_scope = "/".join(cred_parts[1:])

        # Get amz_date from headers
        amz_date = headers.get("x-amz-date", "")

        # Rebuild canonical request
        signed_header_keys = signed_headers_str.split(";")
        canonical_headers = ""
        for k in signed_header_keys:
            canonical_headers += f"{k}:{headers.get(k, '')}\n"

        canonical_request = (
            f"{method}\n"
            f"{path}\n"
            f"{query_string}\n"
            f"{canonical_headers}\n"
            f"{signed_headers_str}\n"
            f"{payload_hash}"
        )

        string_to_sign = (
            f"AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        signing_key = _hmac_sha256(
            _hmac_sha256(
                _hmac_sha256(
                    _hmac_sha256(f"AWS4{secret_key}".encode(), date_stamp),
                    region,
                ),
                service,
            ),
            "aws4_request",
        )

        expected_signature = hmac_mod.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        return hmac_mod.compare_digest(expected_signature, provided_signature)

    except Exception as e:
        logger.warning("Signature verification failed: %s", e)
        return False


async def authenticate_request(request: Request) -> dict:
    """
    Authenticate an S3 request via AWS4-HMAC-SHA256 or admin token.
    Returns the access key record.
    """
    auth_header = request.headers.get("authorization", "")

    # Admin token bypass (for internal NSO operations)
    if auth_header == f"Bearer {settings.ADMIN_TOKEN}" and settings.ADMIN_TOKEN:
        return {
            "access_key_id": "__admin__",
            "owner_id": "__admin__",
            "owner_type": "admin",
            "active": 1,
            "allowed_buckets": "[]",
        }

    if not auth_header.startswith("AWS4-HMAC-SHA256"):
        raise HTTPException(status_code=403, detail="Missing or invalid authorization")

    # Extract access key from credential
    try:
        cred_part = auth_header.split("Credential=")[1].split(",")[0].strip()
        access_key_id = cred_part.split("/")[0]
    except (IndexError, ValueError):
        raise HTTPException(status_code=403, detail="Invalid authorization header")

    key_record = await get_key_by_access_id(access_key_id)
    if not key_record:
        raise HTTPException(status_code=403, detail="Unknown access key")

    if not key_record["active"]:
        raise HTTPException(status_code=403, detail="Access key is revoked")

    # Build headers dict for verification
    lower_headers = {k.lower(): v for k, v in request.headers.items()}

    # Get payload hash
    payload_hash = lower_headers.get("x-amz-content-sha256", "")
    if not payload_hash:
        payload_hash = hashlib.sha256(b"").hexdigest()

    # Build path — the full path as sent by the client
    path = request.url.path
    query_string = str(request.url.query) if request.url.query else ""

    ok = verify_aws4_signature(
        method=request.method,
        path=path,
        query_string=query_string,
        headers=lower_headers,
        payload_hash=payload_hash,
        secret_key=key_record["secret_key"],
        auth_header=auth_header,
    )

    if not ok:
        raise HTTPException(status_code=403, detail="Signature verification failed")

    return key_record


def check_bucket_access(key_record: dict, bucket: str) -> bool:
    """Check if the key has access to the given bucket."""
    if key_record.get("owner_type") == "admin":
        return True
    allowed = key_record.get("allowed_buckets", "[]")
    if isinstance(allowed, str):
        import json
        try:
            allowed = json.loads(allowed)
        except (json.JSONDecodeError, TypeError):
            allowed = []
    if not allowed:
        return True  # empty = all buckets
    return bucket in allowed
