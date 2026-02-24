"""Cloudflare API provider — DNS record management."""
import logging

import httpx

from core.errors import ProviderError

logger = logging.getLogger("setupo.cloudflare")

BASE = "https://api.cloudflare.com/client/v4"


class CloudflareProvider:
    """Manages DNS records via Cloudflare API.

    Can be initialized with a global token (from env) or per-user token
    (user provides their own CF API token for their zone).
    """

    def __init__(self, api_token: str):
        self.api_token = api_token
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=15.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = await self.client.request(method, path, **kwargs)
            data = resp.json()
            if not data.get("success", False):
                errors = data.get("errors", [])
                msg = errors[0].get("message", "Unknown error") if errors else resp.text
                logger.error("Cloudflare %s %s → %s", method, path, msg)
                raise ProviderError("cloudflare", msg)
            return data
        except httpx.HTTPError as e:
            raise ProviderError("cloudflare", str(e))

    # ── Zones ────────────────────────────────────────────────────

    async def list_zones(self, name: str | None = None) -> list[dict]:
        params = {"per_page": 50}
        if name:
            params["name"] = name
        data = await self._request("GET", "/zones", params=params)
        return data.get("result", [])

    async def get_zone_by_domain(self, domain: str) -> dict | None:
        """Find the zone for a domain (walks up subdomains)."""
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            zone_name = ".".join(parts[i:])
            zones = await self.list_zones(name=zone_name)
            if zones:
                return zones[0]
        return None

    # ── DNS Records ──────────────────────────────────────────────

    async def create_dns_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
        proxied: bool = False,
        ttl: int = 1,  # 1 = auto
    ) -> dict:
        data = await self._request("POST", f"/zones/{zone_id}/dns_records", json={
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
            "ttl": ttl,
        })
        record = data.get("result", {})
        logger.info("Created DNS %s record: %s → %s", record_type, name, content)
        return record

    async def update_dns_record(
        self,
        zone_id: str,
        record_id: str,
        record_type: str,
        name: str,
        content: str,
        proxied: bool = False,
    ) -> dict:
        data = await self._request("PUT", f"/zones/{zone_id}/dns_records/{record_id}", json={
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
        })
        return data.get("result", {})

    async def delete_dns_record(self, zone_id: str, record_id: str) -> bool:
        await self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
        logger.info("Deleted DNS record %s from zone %s", record_id, zone_id)
        return True

    async def list_dns_records(self, zone_id: str, name: str | None = None) -> list[dict]:
        params = {"per_page": 100}
        if name:
            params["name"] = name
        data = await self._request("GET", f"/zones/{zone_id}/dns_records", params=params)
        return data.get("result", [])

    async def find_record(self, zone_id: str, name: str, record_type: str = "A") -> dict | None:
        records = await self.list_dns_records(zone_id, name=name)
        for r in records:
            if r.get("type") == record_type:
                return r
        return None
