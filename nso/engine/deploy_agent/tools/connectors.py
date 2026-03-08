"""
Connector tools — setup and manage external service connectors.

Tools:
  - setup_connector: Install and configure a connector (github, s3, slack, cloudflare, r2)
  - list_connectors: List installed connectors with status
  - manage_dns: Manage DNS records via user's Cloudflare connector
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nso.shared import db

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext


def create_connector_tools(ctx: DeployContext) -> list[tuple]:
    """Create connector management tools bound to project context."""

    async def setup_connector(connector_id: str, config_json: str) -> str:
        """Install and configure a connector with credentials. connector_id must be github, s3, slack, cloudflare, or r2. config_json is a JSON object with the credentials."""
        try:
            config = json.loads(config_json) if isinstance(config_json, str) else config_json
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON for config"})

        valid_connectors = {"github", "s3", "slack", "cloudflare", "r2"}
        if connector_id not in valid_connectors:
            return json.dumps({"error": f"Unknown connector: {connector_id}. Valid: {', '.join(sorted(valid_connectors))}"})

        existing = await db.fetch_one("addons", project_id=ctx.project_id, addon_id=connector_id, addon_type="connector")

        connector_names = {
            "github": "GitHub", "s3": "Amazon S3", "slack": "Slack",
            "cloudflare": "Cloudflare", "r2": "Cloudflare R2",
        }

        if not existing:
            import secrets as token_gen
            addon_data = {
                "id": f"adn_{token_gen.token_hex(8)}",
                "project_id": ctx.project_id,
                "addon_id": connector_id,
                "addon_type": "connector",
                "name": connector_names.get(connector_id, connector_id),
                "description": "",
                "version": "1.0.0",
                "category": "",
                "enabled": True,
                "config": config,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.insert("addons", addon_data)
        else:
            old_config = existing.get("config", {})
            if isinstance(old_config, str):
                try:
                    old_config = json.loads(old_config)
                except Exception:
                    old_config = {}
            merged = {**old_config, **config}
            await db.update("addons", existing["id"], {"config": merged})
            config = merged

        # Sync to project_secrets
        from nso.engine.addons.routes_addons.catalog import _sync_connector_secrets
        await _sync_connector_secrets(ctx.project_id, connector_id, config)

        # Test the connection
        from nso.engine.addons.routes_addons.connectors import _TESTERS
        tester = _TESTERS.get(connector_id)
        test_result = {"ok": False, "message": "No tester available"}
        if tester:
            try:
                test_result = await tester(config)
            except Exception as e:
                test_result = {"ok": False, "message": str(e)}

        return json.dumps({
            "ok": True,
            "connector": connector_id,
            "installed": True,
            "configured": True,
            "test": test_result,
            "secrets_synced": True,
        })

    async def list_connectors() -> str:
        """List all installed connectors with their connection status."""
        installed = await db.fetch_all("addons", project_id=ctx.project_id, addon_type="connector")
        connectors = []
        for addon in installed:
            config = addon.get("config", {})
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except Exception:
                    config = {}
            has_config = len(config) > 0
            connectors.append({
                "connector_id": addon["addon_id"],
                "name": addon["name"],
                "enabled": addon.get("enabled", False),
                "configured": has_config,
                "config_keys": list(config.keys()),
            })
        return json.dumps({"connectors": connectors, "count": len(connectors)})

    async def manage_dns(
        action: str,
        domain: str = "",
        record_type: str = "A",
        content: str = "",
        zone_id: str = "",
        record_id: str = "",
        proxied: str = "true",
    ) -> str:
        """Manage DNS records via user's Cloudflare connector.

        Actions:
          - list_zones: List all DNS zones (domains) in the user's Cloudflare account
          - list_records: List DNS records in a zone (requires zone_id)
          - create: Create a DNS record (requires zone_id, domain, content, record_type)
          - update: Update a DNS record (requires zone_id, record_id, domain, content)
          - delete: Delete a DNS record (requires zone_id, record_id)
          - find_zone: Find the zone_id for a domain (requires domain)
        """
        import httpx

        # Check Cloudflare connector is installed
        addon = await db.fetch_one("addons", project_id=ctx.project_id, addon_id="cloudflare", addon_type="connector")
        if not addon or not addon.get("enabled"):
            return json.dumps({
                "error": "Cloudflare connector not configured. The user needs to connect their Cloudflare account first.",
                "hint": "Ask the user for their Cloudflare API token, then use setup_connector('cloudflare', '{\"api_token\": \"...\"}') to configure it.",
            })

        config = addon.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                config = {}

        api_token = config.get("api_token", "")
        headers = {}
        if api_token:
            headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        elif config.get("api_key") and config.get("email"):
            headers = {"X-Auth-Key": config["api_key"], "X-Auth-Email": config["email"], "Content-Type": "application/json"}
        else:
            return json.dumps({"error": "Cloudflare connector missing credentials (api_token or api_key+email)"})

        is_proxied = proxied.lower() in ("true", "1", "yes")

        try:
            async with httpx.AsyncClient(timeout=10) as c:
                if action == "list_zones":
                    resp = await c.get("https://api.cloudflare.com/client/v4/zones",
                                       params={"per_page": 50, "status": "active"}, headers=headers)
                    d = resp.json()
                    if not d.get("success"):
                        return json.dumps({"error": f"Cloudflare error: {d.get('errors', [{}])[0].get('message', '')}"})
                    zones = [{"id": z["id"], "name": z["name"], "status": z["status"]} for z in d.get("result", [])]
                    return json.dumps({"zones": zones, "count": len(zones)})

                elif action == "find_zone":
                    if not domain:
                        return json.dumps({"error": "domain is required for find_zone"})
                    # Try parent domains: sub.example.com → example.com → com
                    parts = domain.split(".")
                    for i in range(len(parts) - 1):
                        candidate = ".".join(parts[i:])
                        resp = await c.get("https://api.cloudflare.com/client/v4/zones",
                                           params={"name": candidate}, headers=headers)
                        d = resp.json()
                        results = d.get("result", [])
                        if results:
                            z = results[0]
                            return json.dumps({"zone_id": z["id"], "zone_name": z["name"], "domain": domain})
                    return json.dumps({"error": f"No Cloudflare zone found for '{domain}'. Make sure the domain is added to the Cloudflare account."})

                elif action == "list_records":
                    if not zone_id:
                        return json.dumps({"error": "zone_id is required for list_records"})
                    params: dict = {"per_page": 100}
                    if domain:
                        params["name"] = domain
                    if record_type:
                        params["type"] = record_type
                    resp = await c.get(f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                                       params=params, headers=headers)
                    d = resp.json()
                    if not d.get("success"):
                        return json.dumps({"error": f"Cloudflare error: {d.get('errors', [{}])[0].get('message', '')}"})
                    records = [{"id": r["id"], "type": r["type"], "name": r["name"],
                                "content": r["content"], "proxied": r.get("proxied", False)} for r in d.get("result", [])]
                    return json.dumps({"records": records, "count": len(records)})

                elif action == "create":
                    if not zone_id or not domain or not content:
                        return json.dumps({"error": "zone_id, domain, and content are required for create"})
                    payload = {"type": record_type, "name": domain, "content": content,
                               "proxied": is_proxied, "ttl": 1}
                    resp = await c.post(f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                                        json=payload, headers=headers)
                    d = resp.json()
                    if not d.get("success"):
                        return json.dumps({"error": f"Cloudflare error: {d.get('errors', [{}])[0].get('message', '')}"})
                    r = d.get("result", {})
                    return json.dumps({"ok": True, "record": {"id": r["id"], "type": r["type"],
                                                               "name": r["name"], "content": r["content"]}})

                elif action == "update":
                    if not zone_id or not record_id:
                        return json.dumps({"error": "zone_id and record_id are required for update"})
                    payload: dict = {"type": record_type, "ttl": 1}
                    if domain:
                        payload["name"] = domain
                    if content:
                        payload["content"] = content
                    payload["proxied"] = is_proxied
                    resp = await c.patch(f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                                         json=payload, headers=headers)
                    d = resp.json()
                    if not d.get("success"):
                        return json.dumps({"error": f"Cloudflare error: {d.get('errors', [{}])[0].get('message', '')}"})
                    return json.dumps({"ok": True, "updated": record_id})

                elif action == "delete":
                    if not zone_id or not record_id:
                        return json.dumps({"error": "zone_id and record_id are required for delete"})
                    resp = await c.delete(f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                                          headers=headers)
                    d = resp.json()
                    if not d.get("success"):
                        return json.dumps({"error": f"Cloudflare error: {d.get('errors', [{}])[0].get('message', '')}"})
                    return json.dumps({"ok": True, "deleted": record_id})

                else:
                    return json.dumps({"error": f"Unknown action '{action}'. Valid: list_zones, find_zone, list_records, create, update, delete"})

        except httpx.TimeoutException:
            return json.dumps({"error": "Cloudflare API timed out"})
        except Exception as e:
            return json.dumps({"error": f"Cloudflare API error: {e}"})

    return [
        (setup_connector, "setup_connector", "Install and configure a connector (github, s3, slack, cloudflare, r2) with credentials"),
        (list_connectors, "list_connectors", "List installed connectors with their connection status"),
        (manage_dns, "manage_dns", "Manage DNS records via user's Cloudflare connector: list zones, create/update/delete records, find zone for domain"),
    ]
