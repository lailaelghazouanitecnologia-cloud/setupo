"""
Connector tools — setup and manage external service connectors.

Tools:
  - setup_connector: Install and configure a connector (github, s3, slack)
  - list_connectors: List installed connectors with status
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
        """Install and configure a connector with credentials. connector_id must be github, s3, or slack. config_json is a JSON object with the credentials."""
        try:
            config = json.loads(config_json) if isinstance(config_json, str) else config_json
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON for config"})

        valid_connectors = {"github", "s3", "slack"}
        if connector_id not in valid_connectors:
            return json.dumps({"error": f"Unknown connector: {connector_id}. Valid: {', '.join(valid_connectors)}"})

        existing = await db.fetch_one("addons", project_id=ctx.project_id, addon_id=connector_id, addon_type="connector")

        if not existing:
            import secrets as token_gen
            addon_data = {
                "id": f"adn_{token_gen.token_hex(8)}",
                "project_id": ctx.project_id,
                "addon_id": connector_id,
                "addon_type": "connector",
                "name": {"github": "GitHub", "s3": "Amazon S3", "slack": "Slack"}[connector_id],
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

    return [
        (setup_connector, "setup_connector", "Install and configure a connector (github, s3, slack) with credentials"),
        (list_connectors, "list_connectors", "List installed connectors with their connection status"),
    ]
