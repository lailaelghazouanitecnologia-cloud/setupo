"""
Infrastructure tools — instance creation, service management, domain management.

Tools:
  - create_instance: Create a new VPS instance
  - manage_service: Start/stop/restart/status systemd services on an instance
  - manage_domain: Add, configure, or remove domains for a workspace
  - link_workspace_instance: Link a workspace to an instance
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import TYPE_CHECKING

from nso.shared import db
from nso.config import settings

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext

logger = logging.getLogger("nso.deploy_agent.tools.infrastructure")


def create_infrastructure_tools(ctx: DeployContext) -> list[tuple]:
    """Create infrastructure management tools bound to project context."""

    async def create_instance(
        label: str = "",
        region: str = "ewr",
        plan: str = "vc2-1c-1gb",
        workspace: str = "",
        source_type: str = "",
        git_url: str = "",
        git_branch: str = "main",
    ) -> str:
        """Create a new VPS instance. Provisions via Vultr. Optional: link to workspace, deploy from git."""
        from nso.shared.models import CreateInstanceRequest, InstanceType
        from nso.engine.compute.service import create_instance as _create

        req = CreateInstanceRequest(
            type=InstanceType.SETUP,
            label=label or f"nso-{workspace or 'app'}",
            region=region,
            plan=plan,
            workspace=workspace or None,
            source_type=source_type or None,
            git_url=git_url or None,
            git_branch=git_branch,
        )

        try:
            instance = await _create(ctx.project_id, req)
        except Exception as e:
            return json.dumps({"error": f"Failed to create instance: {e}"})

        # Link workspace to instance if specified
        if workspace:
            ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
            if ws:
                await db.update("workspaces", ws["id"], {"instance_id": instance.id})

        return json.dumps({
            "ok": True,
            "instance_id": instance.id,
            "label": instance.label,
            "region": instance.region,
            "plan": instance.plan,
            "state": instance.state.value,
            "workspace": workspace,
            "message": f"Instance '{instance.label}' is being provisioned. It will be ready in ~2 minutes.",
        })

    async def manage_service(instance_id: str, action: str, service_name: str) -> str:
        """Manage a systemd service on an instance. action: start, stop, restart, status."""
        if action not in ("start", "stop", "restart", "status"):
            return json.dumps({"error": f"Invalid action '{action}'. Must be: start, stop, restart, status"})

        inst = await db.fetch_one("instances", id=instance_id)
        if not inst or inst.get("project_id") != ctx.project_id:
            return json.dumps({"error": f"Instance {instance_id} not found"})

        ip = inst.get("ip")
        if not ip:
            return json.dumps({"error": "Instance has no IP address (still provisioning?)"})

        import httpx
        agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")

        # Try localhost first, then public IP
        for base_url in [f"http://127.0.0.1:8081", f"http://{ip}:8081"]:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base_url}/auth/login", json={
                        "email": settings.ADMIN_EMAIL, "password": agent_password,
                    })
                if resp.status_code != 200:
                    continue

                token = resp.json()["token"]
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{base_url}/exec/service",
                        params={"action": action, "name": service_name},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                if resp.status_code == 200:
                    return json.dumps({
                        "ok": True,
                        "service": service_name,
                        "action": action,
                        "result": resp.json(),
                    })
                return json.dumps({"error": f"Service {action} failed: {resp.text[:300]}"})
            except Exception:
                continue

        return json.dumps({"error": f"Cannot reach agent on instance {instance_id}"})

    async def manage_domain(
        workspace: str = "",
        action: str = "auto",
        custom_domain: str = "",
        instance_id: str = "",
    ) -> str:
        """Manage domain for a workspace. action: auto (assign workspace.user.nso.dev), custom (set custom domain), remove, list.

        Auto-domain pattern: workspace-username.nso.dev (uses platform Cloudflare).
        For custom domains: if user has a Cloudflare connector, use manage_dns tool instead for full control.
        """
        if action == "list":
            domains = await db.fetch_all("domains", project_id=ctx.project_id)
            result = []
            for d in domains:
                result.append({
                    "domain": d.get("domain", ""),
                    "record_type": d.get("record_type", ""),
                    "value": d.get("value", ""),
                    "instance_id": d.get("instance_id", ""),
                    "managed": bool(d.get("managed", 0)),
                })
            # Also check if user has Cloudflare connector
            cf_addon = await db.fetch_one("addons", project_id=ctx.project_id, addon_id="cloudflare", addon_type="connector")
            has_cf = bool(cf_addon and cf_addon.get("enabled"))
            return json.dumps({"domains": result, "count": len(result), "has_cloudflare_connector": has_cf})

        if not workspace:
            return json.dumps({"error": "workspace name is required"})

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        # Resolve instance
        if not instance_id:
            instance_id = ws.get("instance_id", "")
        if not instance_id:
            instances = await db.fetch_all("instances", project_id=ctx.project_id)
            ready = [i for i in instances if i.get("state") in ("ready", "running")]
            if ready:
                instance_id = ready[0]["id"]

        if not instance_id:
            return json.dumps({"error": "No instance found. Create or link one first."})

        inst = await db.fetch_one("instances", id=instance_id)
        if not inst:
            return json.dumps({"error": f"Instance {instance_id} not found"})

        ip = inst.get("ip", "")
        if not ip:
            return json.dumps({"error": "Instance has no IP (still provisioning?)"})

        if action == "remove":
            domains = await db.fetch_all("domains", project_id=ctx.project_id)
            removed = []
            for d in domains:
                if workspace in d.get("domain", ""):
                    if d.get("cf_record_id") and settings.CF_API_TOKEN:
                        try:
                            from nso.engine.dns.service import CloudflareProvider
                            cf = CloudflareProvider(settings.CF_API_TOKEN)
                            await cf.delete_dns_record(d.get("cf_zone_id", settings.CF_NSO_ZONE_ID), d["cf_record_id"])
                            await cf.close()
                        except Exception:
                            pass
                    await db.delete("domains", d["id"])
                    removed.append(d["domain"])
            return json.dumps({"ok": True, "removed": removed})

        # action = "auto" or "custom"
        from nso.engine.deploy_agent.tools.deploy import _auto_claim_subdomain, _auto_assign_domain

        if ctx.user_id:
            await _auto_claim_subdomain(ctx.user_id)

        domain = await _auto_assign_domain(
            ctx.project_id, ctx.user_id, workspace,
            instance_id, ip, custom_domain if action == "custom" else "",
        )

        return json.dumps({
            "ok": True,
            "workspace": workspace,
            "domain": domain,
            "instance_id": instance_id,
            "ip": ip,
            "pattern": "workspace-username.nso.dev" if action == "auto" else "custom",
        })

    async def link_workspace_instance(workspace: str, instance_id: str) -> str:
        """Link a workspace to an instance for deployments."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        inst = await db.fetch_one("instances", id=instance_id)
        if not inst or inst.get("project_id") != ctx.project_id:
            return json.dumps({"error": f"Instance {instance_id} not found"})

        await db.update("workspaces", ws["id"], {"instance_id": instance_id})

        return json.dumps({
            "ok": True,
            "workspace": workspace,
            "instance_id": instance_id,
            "instance_label": inst.get("label", ""),
            "ip": inst.get("ip", ""),
        })

    return [
        (create_instance, "create_instance", "Create a new VPS instance (Vultr). Specify label, region, plan, workspace."),
        (manage_service, "manage_service", "Start/stop/restart/status a systemd service on an instance"),
        (manage_domain, "manage_domain", "Manage domain: auto-assign workspace.user.nso.dev, set custom domain, remove, or list domains"),
        (link_workspace_instance, "link_workspace_instance", "Link a workspace to an instance for deployments"),
    ]
