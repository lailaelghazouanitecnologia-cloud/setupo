import logging
from typing import Any

import httpx

from core.errors import ProviderError
from core.providers.base import CloudProvider
from server.config import settings

logger = logging.getLogger("nso.vultr")

BASE = settings.VULTR_BASE_URL
REQUEST_TIMEOUT = 30.0


class VultrProvider(CloudProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.VULTR_API_KEY
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # Force IPv4 — Vultr API key may not authorize IPv6 addresses
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            self._client = httpx.AsyncClient(
                base_url=BASE,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=REQUEST_TIMEOUT,
                transport=transport,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict | None:
        try:
            resp = await self.client.request(method, path, **kwargs)
            if resp.status_code == 204:
                return None
            if resp.status_code >= 400:
                body = resp.text
                logger.error("Vultr %s %s → %d: %s", method, path, resp.status_code, body)
                raise ProviderError("vultr", f"HTTP {resp.status_code}: {body}")
            return resp.json() if resp.text else None
        except httpx.HTTPError as e:
            raise ProviderError("vultr", str(e))

    async def create_instance(
        self,
        region: str = "ewr",
        plan: str = "vc2-1c-1gb",
        os_id: int = 2284,
        label: str = "",
        ssh_key_ids: list[str] | None = None,
        user_data: str = "",
        tag: str = "nso",
        **kwargs,
    ) -> dict:
        payload: dict[str, Any] = {
            "region": region,
            "plan": plan,
            "os_id": os_id,
            "label": label or "nso-instance",
            "tag": tag,
            "backups": "disabled",
            "enable_ipv6": True,
        }
        if ssh_key_ids:
            payload["sshkey_id"] = ssh_key_ids
        if user_data:
            payload["user_data"] = user_data

        data = await self._request("POST", "/instances", json=payload)
        instance = data.get("instance", {})
        logger.info("Created Vultr instance %s in %s", instance.get("id"), region)
        return instance

    async def get_instance(self, instance_id: str) -> dict | None:
        data = await self._request("GET", f"/instances/{instance_id}")
        return data.get("instance") if data else None

    async def delete_instance(self, instance_id: str) -> bool:
        await self._request("DELETE", f"/instances/{instance_id}")
        logger.info("Deleted Vultr instance %s", instance_id)
        return True

    async def list_instances(self, tag: str = "nso") -> list[dict]:
        data = await self._request("GET", "/instances", params={"tag": tag, "per_page": 100})
        return data.get("instances", []) if data else []

    async def start_instance(self, instance_id: str) -> bool:
        await self._request("POST", f"/instances/{instance_id}/start")
        return True

    async def stop_instance(self, instance_id: str) -> bool:
        await self._request("POST", f"/instances/{instance_id}/halt")
        return True

    async def restart_instance(self, instance_id: str) -> bool:
        await self._request("POST", f"/instances/{instance_id}/reboot")
        return True

    async def create_ssh_key(self, name: str, public_key: str) -> dict:
        data = await self._request("POST", "/ssh-keys", json={
            "name": name,
            "ssh_key": public_key,
        })
        return data.get("ssh_key", {})

    async def delete_ssh_key(self, key_id: str) -> bool:
        await self._request("DELETE", f"/ssh-keys/{key_id}")
        return True

    async def list_ssh_keys(self) -> list[dict]:
        data = await self._request("GET", "/ssh-keys")
        return data.get("ssh_keys", []) if data else []

    async def list_regions(self) -> list[dict]:
        data = await self._request("GET", "/regions")
        return data.get("regions", []) if data else []

    async def list_plans(self, plan_type: str = "vc2") -> list[dict]:
        data = await self._request("GET", "/plans", params={"type": plan_type, "per_page": 100})
        return data.get("plans", []) if data else []

    async def list_os(self) -> list[dict]:
        data = await self._request("GET", "/os")
        return data.get("os", []) if data else []

    async def create_startup_script(self, name: str, script: str, script_type: str = "boot") -> dict:
        data = await self._request("POST", "/startup-scripts", json={
            "name": name,
            "script": script,
            "type": script_type,
        })
        return data.get("startup_script", {})

    async def delete_startup_script(self, script_id: str) -> bool:
        await self._request("DELETE", f"/startup-scripts/{script_id}")
        return True
