"""Zar Storage — Cloudflare R2 client (S3-compatible).

Handles upload, download, list, and delete of .zar packages.
Uses AWS S3v4 signature with httpx — no boto3 dependency.

Bucket structure:
    {project_id}/{workspace}/{branch}/v{version}.zar
    {project_id}/{workspace}/{branch}/latest.zar
    {project_id}/{workspace}/branches.json
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from core.models import R2Config, ZarManifest

logger = logging.getLogger("setupo.zar.storage")


class R2Client:
    """Cloudflare R2 storage client using S3v4 signatures."""

    def __init__(self, config: R2Config):
        self.config = config
        self.bucket = config.bucket
        self.endpoint = config.endpoint.rstrip("/")
        self.access_key = config.access_key_id
        self.secret_key = config.secret_access_key
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── S3v4 Signing ─────────────────────────────────────────────

    def _sign(self, method: str, path: str, headers: dict, payload_hash: str) -> dict:
        """Generate AWS S3v4 signature headers."""
        now = datetime.now(timezone.utc)
        date_stamp = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        region = "auto"  # R2 uses "auto"
        service = "s3"

        # Host from endpoint
        host = self.endpoint.replace("https://", "").replace("http://", "")

        headers_to_sign = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        headers_to_sign.update({k.lower(): v for k, v in headers.items()})

        signed_header_keys = sorted(headers_to_sign.keys())
        signed_headers = ";".join(signed_header_keys)
        canonical_headers = "".join(
            f"{k}:{headers_to_sign[k]}\n" for k in signed_header_keys
        )

        canonical_request = (
            f"{method}\n"
            f"/{self.bucket}/{quote(path, safe='/')}\n"
            f"\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )

        credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        def _hmac_sha256(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        signing_key = _hmac_sha256(
            _hmac_sha256(
                _hmac_sha256(
                    _hmac_sha256(f"AWS4{self.secret_key}".encode(), date_stamp),
                    region,
                ),
                service,
            ),
            "aws4_request",
        )

        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        auth_header = (
            f"AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        return {
            "Authorization": auth_header,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }

    # ── Operations ───────────────────────────────────────────────

    async def upload(self, key: str, data: bytes, content_type: str = "application/gzip") -> bool:
        """Upload bytes to R2."""
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = {"Content-Type": content_type}
        sign_headers = self._sign("PUT", key, headers, payload_hash)
        headers.update(sign_headers)

        url = f"{self.endpoint}/{self.bucket}/{quote(key, safe='/')}"
        resp = await self.client.put(url, content=data, headers=headers)

        if resp.status_code in (200, 201):
            logger.info("Uploaded %s (%d bytes)", key, len(data))
            return True
        logger.error("Upload failed %s: %d %s", key, resp.status_code, resp.text[:200])
        return False

    async def download(self, key: str) -> bytes | None:
        """Download bytes from R2."""
        payload_hash = hashlib.sha256(b"").hexdigest()
        sign_headers = self._sign("GET", key, {}, payload_hash)

        url = f"{self.endpoint}/{self.bucket}/{quote(key, safe='/')}"
        resp = await self.client.get(url, headers=sign_headers)

        if resp.status_code == 200:
            logger.info("Downloaded %s (%d bytes)", key, len(resp.content))
            return resp.content
        if resp.status_code == 404:
            return None
        logger.error("Download failed %s: %d", key, resp.status_code)
        return None

    async def delete(self, key: str) -> bool:
        """Delete an object from R2."""
        payload_hash = hashlib.sha256(b"").hexdigest()
        sign_headers = self._sign("DELETE", key, {}, payload_hash)

        url = f"{self.endpoint}/{self.bucket}/{quote(key, safe='/')}"
        resp = await self.client.delete(url, headers=sign_headers)
        return resp.status_code in (200, 204)

    async def exists(self, key: str) -> bool:
        """Check if an object exists in R2."""
        payload_hash = hashlib.sha256(b"").hexdigest()
        sign_headers = self._sign("HEAD", key, {}, payload_hash)

        url = f"{self.endpoint}/{self.bucket}/{quote(key, safe='/')}"
        resp = await self.client.head(url, headers=sign_headers)
        return resp.status_code == 200

    async def list_keys(self, prefix: str) -> list[str]:
        """List object keys with a prefix."""
        payload_hash = hashlib.sha256(b"").hexdigest()
        sign_headers = self._sign("GET", "", {}, payload_hash)

        url = f"{self.endpoint}/{self.bucket}?prefix={quote(prefix)}&list-type=2"
        resp = await self.client.get(url, headers=sign_headers)

        if resp.status_code != 200:
            return []

        # Parse XML response (minimal — just extract <Key> tags)
        keys = []
        text = resp.text
        while "<Key>" in text:
            start = text.index("<Key>") + 5
            end = text.index("</Key>", start)
            keys.append(text[start:end])
            text = text[end:]
        return keys

    # ── Zar-specific operations ──────────────────────────────────

    def _zar_key(self, project_id: str, workspace: str, branch: str, version: str) -> str:
        """Build the R2 key for a .zar package."""
        return f"{project_id}/{workspace}/{branch}/v{version}.zar"

    def _latest_key(self, project_id: str, workspace: str, branch: str) -> str:
        return f"{project_id}/{workspace}/{branch}/latest.zar"

    def _branches_key(self, project_id: str, workspace: str) -> str:
        return f"{project_id}/{workspace}/branches.json"

    async def upload_zar(
        self,
        project_id: str,
        workspace: str,
        branch: str,
        version: str,
        zar_bytes: bytes,
    ) -> str:
        """Upload a .zar and update latest + branches.json. Returns the R2 key."""
        key = self._zar_key(project_id, workspace, branch, version)
        latest_key = self._latest_key(project_id, workspace, branch)

        # Upload versioned
        ok = await self.upload(key, zar_bytes)
        if not ok:
            raise RuntimeError(f"Failed to upload {key}")

        # Upload as latest
        await self.upload(latest_key, zar_bytes)

        # Update branches.json
        branches_key = self._branches_key(project_id, workspace)
        branches_data = await self.download(branches_key)
        branches = json.loads(branches_data) if branches_data else {}
        branches[branch] = version
        await self.upload(
            branches_key,
            json.dumps(branches, indent=2).encode(),
            content_type="application/json",
        )

        logger.info("Uploaded zar %s/%s@%s v%s", project_id, workspace, branch, version)
        return key

    async def download_zar(
        self,
        project_id: str,
        workspace: str,
        branch: str,
        version: str | None = None,
    ) -> bytes | None:
        """Download a .zar — specific version or latest."""
        if version:
            key = self._zar_key(project_id, workspace, branch, version)
        else:
            key = self._latest_key(project_id, workspace, branch)
        return await self.download(key)

    async def list_versions(self, project_id: str, workspace: str, branch: str) -> list[str]:
        """List all versions of a workspace on a branch."""
        prefix = f"{project_id}/{workspace}/{branch}/v"
        keys = await self.list_keys(prefix)
        versions = []
        for k in keys:
            # Extract version from key like "proj/ws/main/v1.2.3.zar"
            filename = k.rsplit("/", 1)[-1]
            if filename.startswith("v") and filename.endswith(".zar"):
                versions.append(filename[1:-4])  # Strip v and .zar
        return sorted(versions)

    async def list_branches(self, project_id: str, workspace: str) -> dict:
        """Get branches.json for a workspace."""
        key = self._branches_key(project_id, workspace)
        data = await self.download(key)
        if data:
            return json.loads(data)
        return {}

    async def copy_branch(
        self,
        project_id: str,
        workspace: str,
        from_branch: str,
        to_branch: str,
    ) -> str | None:
        """Copy latest .zar from one branch to another (for branching)."""
        zar_bytes = await self.download_zar(project_id, workspace, from_branch)
        if not zar_bytes:
            return None
        return await self.upload_zar(project_id, workspace, to_branch, "0.1.0", zar_bytes)
