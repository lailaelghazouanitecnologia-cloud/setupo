"""
Deploy tools — build, ship, status, validation.

Tools:
  - run_build: Trigger smart build for a workspace
  - run_ship: Full ship pipeline (pack → push → deploy)
  - check_deploy_status: Check deploy state on instance
  - run_validation: Run validation checks
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from nso.shared import db
from nso.config import settings

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext

logger = logging.getLogger("nso.deploy_agent.tools.deploy")


def create_deploy_tools(ctx: DeployContext) -> list[tuple]:
    """Create deploy pipeline tools bound to project context."""

    async def run_build(workspace: str, build_command: str = "") -> str:
        """Trigger a build for a workspace."""
        from nso.engine.build.service import execute_build
        from nso.engine.storage.zar_packer import pack
        from nso.engine.workspace.config import read_config, read_package_config
        from nso.engine.deploy_agent.tools.workspace import _detect_build_cmd

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        pkg_config = read_package_config(ws_path)
        config = read_config(ws_path)
        stack = config.type if config else ""

        try:
            zar_bytes, manifest = pack(
                workspace_path=ws_path,
                version=pkg_config.version if pkg_config else None,
                branch="main",
                project_id=ctx.project_id,
            )
        except FileNotFoundError:
            return json.dumps({"error": f"Workspace directory not found: {ws_path}"})

        if not build_command:
            build_command = _detect_build_cmd(ws_path)
        if not build_command:
            return json.dumps({"ok": True, "strategy": "none", "message": "No build step needed"})

        result = await execute_build(
            project_id=ctx.project_id,
            workspace=workspace,
            zar_bytes=zar_bytes,
            build_command=build_command,
            stack=stack,
        )
        return json.dumps(result)

    async def run_ship(workspace: str, instance_id: str = "", branch: str = "main", domain: str = "") -> str:
        """Execute full ship pipeline: pack → push to R2 → deploy to instance."""
        from nso.engine.storage.zar_packer import pack
        from nso.engine.storage.service import R2Client
        from nso.engine.workspace.config import read_config, read_package_config

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path:
            return json.dumps({"error": "Workspace has no path"})

        # Auto-claim subdomain
        if ctx.user_id:
            await _auto_claim_subdomain(ctx.user_id)

        # Resolve instance
        if not instance_id:
            if ws.get("instance_id"):
                instance_id = ws["instance_id"]
            else:
                config = read_config(ws_path)
                if config and config.deploy and config.deploy.instance_id:
                    instance_id = config.deploy.instance_id
                else:
                    instances = await db.fetch_all("instances", project_id=ctx.project_id)
                    ready = [i for i in instances if i.get("state") in ("ready", "running")]
                    if ready:
                        instance_id = ready[0]["id"]
                    else:
                        return json.dumps({"error": "No instance available. Create one first."})

        inst = await db.fetch_one("instances", id=instance_id)
        if not inst or inst.get("project_id") != ctx.project_id:
            return json.dumps({"error": f"Instance {instance_id} not found in project"})
        if inst.get("state") not in ("ready", "running"):
            return json.dumps({"error": f"Instance is in state '{inst.get('state')}' — must be ready or running"})

        # Pack
        pkg_config = read_package_config(ws_path)
        try:
            zar_bytes, manifest = pack(
                workspace_path=ws_path,
                version=pkg_config.version if pkg_config else None,
                branch=branch,
                project_id=ctx.project_id,
            )
        except FileNotFoundError:
            return json.dumps({"error": f"Workspace directory not found: {ws_path}"})

        # Push to R2
        r2 = R2Client(settings.r2_config())
        try:
            r2_key = await r2.upload_zar(ctx.project_id, workspace, branch, manifest.version, zar_bytes)
        except RuntimeError as exc:
            return json.dumps({"error": f"R2 upload failed: {exc}"})
        finally:
            await r2.close()

        # Deploy via agent
        import httpx
        agent_url = f"http://{inst['ip']}:8081"
        agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")

        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(timeout=15, transport=transport) as client:
                resp = await client.post(f"{agent_url}/auth/login", json={
                    "email": settings.ADMIN_EMAIL,
                    "password": agent_password,
                })
            if resp.status_code != 200:
                return json.dumps({"error": f"Agent auth failed (HTTP {resp.status_code})"})
            token = resp.json()["token"]
        except Exception as exc:
            return json.dumps({"error": f"Cannot connect to agent: {exc}"})

        # Resolve secrets
        resolved_secrets: dict[str, str] = {}
        try:
            rows = await db.fetch_all("project_secrets", project_id=ctx.project_id)
            for row in rows:
                k, v = row.get("key", ""), row.get("value", "")
                if k:
                    resolved_secrets[k] = v
        except Exception:
            pass

        r2_cfg = settings.r2_config()
        await db.update("instances", instance_id, {"state": "deploying", "workspace": workspace})

        try:
            async with httpx.AsyncClient(timeout=300, transport=transport) as client:
                resp = await client.post(
                    f"{agent_url}/deploy/pull",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "r2_key": r2_key,
                        "r2_endpoint": r2_cfg.endpoint,
                        "r2_bucket": r2_cfg.bucket,
                        "r2_access_key_id": r2_cfg.access_key_id,
                        "r2_secret_access_key": r2_cfg.secret_access_key,
                        "target_dir": "/opt/app",
                        "restart_service": "nso-app",
                        "install_deps": True,
                        "secrets": resolved_secrets,
                        "use_pipeline": True,
                    },
                )
            if resp.status_code != 200:
                await db.update("instances", instance_id, {"state": "error", "error": "deploy failed"})
                return json.dumps({"error": f"Deploy failed: {resp.text[:500]}"})

            deploy_result = resp.json()
        except Exception as exc:
            await db.update("instances", instance_id, {"state": "error", "error": str(exc)})
            return json.dumps({"error": f"Deploy error: {exc}"})

        await db.update("instances", instance_id, {"state": "running", "error": ""})

        deploy_domain = await _auto_assign_domain(
            ctx.project_id, ctx.user_id, workspace, instance_id, inst.get("ip", ""), domain,
        )

        return json.dumps({
            "ok": True,
            "workspace": workspace,
            "version": manifest.version,
            "branch": branch,
            "r2_key": r2_key,
            "instance_id": instance_id,
            "domain": deploy_domain,
            "snapshot": deploy_result.get("snapshot", ""),
            "pipeline": deploy_result.get("pipeline", False),
        })

    async def check_deploy_status(instance_id: str) -> str:
        """Check the current deploy state on an instance."""
        inst = await db.fetch_one("instances", id=instance_id)
        if not inst or inst.get("project_id") != ctx.project_id:
            return json.dumps({"error": "Instance not found"})

        ip = inst.get("ip", "")
        if not ip:
            return json.dumps({"error": "Instance has no IP"})

        try:
            import httpx
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")
            async with httpx.AsyncClient(timeout=10, transport=transport) as client:
                resp = await client.post(f"http://{ip}:8081/auth/login", json={
                    "email": settings.ADMIN_EMAIL, "password": agent_password,
                })
                if resp.status_code != 200:
                    return json.dumps({"error": "Agent auth failed"})
                token = resp.json()["token"]

                resp = await client.get(
                    f"http://{ip}:8081/deploy/current",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    return json.dumps(resp.json())
                return json.dumps({"error": f"Status check failed: {resp.status_code}"})
        except Exception as exc:
            return json.dumps({"error": f"Cannot reach agent: {exc}"})

    async def run_validation(workspace: str = "", checks: str = "") -> str:
        """Run validation checks on a workspace using validate.toml or inline checks JSON array."""
        from nso.engine.validator import service as validator_service

        context: dict = {"project_id": ctx.project_id}
        validations = []

        if workspace:
            ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
            if ws:
                ws_path = ws.get("path", "")
                context["workspace"] = workspace
                if ws.get("instance_id"):
                    inst = await db.fetch_one("instances", id=ws["instance_id"])
                    if inst:
                        context["ip"] = inst.get("ip", "")

                domains = await db.fetch_all("domains", project_id=ctx.project_id)
                for dom in domains:
                    if workspace in dom.get("domain", ""):
                        context["domain"] = dom["domain"]
                        break

                toml_path = os.path.join(ws_path, "validate.toml") if ws_path else ""
                if toml_path and os.path.isfile(toml_path):
                    try:
                        content = Path(toml_path).read_text()
                        validations = validator_service.parse_validate_toml(content, ctx.project_id)
                    except Exception as e:
                        return json.dumps({"error": f"Invalid validate.toml: {e}"})

        if checks:
            try:
                check_list = json.loads(checks)
                if isinstance(check_list, list):
                    validations = [
                        validator_service.Validation(
                            name=c.get("name", "check"),
                            type=c.get("type", "http"),
                            config={k: v for k, v in c.items() if k not in ("name", "type")},
                            project_id=ctx.project_id,
                        )
                        for c in check_list
                    ]
            except json.JSONDecodeError:
                return json.dumps({"error": "Invalid JSON for checks parameter"})

        if not validations:
            return json.dumps({"error": "No checks found. Create a validate.toml or pass inline checks."})

        run = await validator_service.execute_batch(
            validations,
            project_id=ctx.project_id,
            workspace=workspace,
            trigger="agent",
            context=context,
            persist=True,
            metadata={"user_id": ctx.user_id},
        )

        return json.dumps(run.to_dict())

    return [
        (run_build, "run_build", "Trigger smart build for a workspace"),
        (run_ship, "run_ship", "Execute full ship: pack + push + deploy + auto-domain"),
        (check_deploy_status, "check_deploy_status", "Check deploy status on an instance"),
        (run_validation, "run_validation", "Run validation checks on a workspace"),
    ]


# ── Internal helpers ──

async def _auto_claim_subdomain(user_id: str):
    """Auto-claim a subdomain for the user if they don't have one."""
    user = await db.fetch_one("users", id=user_id)
    if not user:
        return
    if user.get("subdomain"):
        return

    import re
    name = user.get("name", "") or user.get("email", "").split("@")[0]
    sub = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    if len(sub) < 3:
        sub = f"user-{user_id[-8:]}"
    sub = sub[:32]

    from nso.engine.auth import service as auth_service
    try:
        available = await auth_service.check_subdomain_available(sub)
        if not available:
            sub = f"{sub}-{user_id[-4:]}"
            available = await auth_service.check_subdomain_available(sub)
        if not available:
            return

        await auth_service.claim_subdomain(user_id, sub)

        if settings.CF_API_TOKEN and settings.CF_NSO_ZONE_ID:
            from nso.engine.dns.service import CloudflareProvider
            full_domain = f"{sub}.{settings.NSO_BASE_DOMAIN}"
            cf = CloudflareProvider(settings.CF_API_TOKEN)
            try:
                await cf.create_dns_record(
                    zone_id=settings.CF_NSO_ZONE_ID,
                    record_type="CNAME",
                    name=full_domain,
                    content=settings.NSO_BASE_DOMAIN,
                    proxied=True,
                )
            except Exception:
                pass
            finally:
                await cf.close()

        logger.info("Auto-claimed subdomain '%s' for user %s", sub, user_id)
    except Exception as e:
        logger.warning("Auto-claim subdomain failed for user %s: %s", user_id, e)


async def _auto_assign_domain(
    project_id: str, user_id: str, workspace: str,
    instance_id: str, ip: str, custom_domain: str,
) -> str:
    """Auto-assign a deploy domain like workspace.user.nso.dev."""
    if not ip or not settings.CF_API_TOKEN or not settings.CF_NSO_ZONE_ID:
        return ""

    if custom_domain:
        deploy_domain = custom_domain
    else:
        project = await db.fetch_one("projects", id=project_id)
        owner_id = project.get("owner", "") if project else user_id
        owner = await db.fetch_one("users", id=owner_id) if owner_id else None
        owner_sub = (owner.get("subdomain", "") if owner else "").strip()

        if owner_sub:
            deploy_domain = f"{workspace}.{owner_sub}.{settings.NSO_BASE_DOMAIN}"
        else:
            short = project_id.replace("proj_", "")[:8]
            deploy_domain = f"{workspace}-{short}.{settings.NSO_BASE_DOMAIN}"

    try:
        from nso.engine.dns.service import CloudflareProvider
        cf = CloudflareProvider(settings.CF_API_TOKEN)
        existing = await cf.find_record(settings.CF_NSO_ZONE_ID, deploy_domain, "A")
        if existing:
            await cf.update_dns_record(
                settings.CF_NSO_ZONE_ID, existing["id"],
                "A", deploy_domain, ip, proxied=True,
            )
            cf_record_id = existing["id"]
        else:
            record = await cf.create_dns_record(
                settings.CF_NSO_ZONE_ID, "A", deploy_domain, ip, proxied=True,
            )
            cf_record_id = record.get("id", "")
        await cf.close()

        dom_existing = await db.fetch_one("domains", project_id=project_id, domain=deploy_domain)
        if dom_existing:
            await db.update("domains", dom_existing["id"], {
                "value": ip, "cf_record_id": cf_record_id,
                "instance_id": instance_id, "managed": 1,
            })
        else:
            await db.insert("domains", {
                "id": f"dom_{uuid.uuid4().hex[:16]}",
                "project_id": project_id,
                "instance_id": instance_id,
                "domain": deploy_domain,
                "record_type": "A",
                "value": ip,
                "cf_zone_id": settings.CF_NSO_ZONE_ID,
                "cf_record_id": cf_record_id,
                "proxied": 1,
                "managed": 1,
            })

        logger.info("Deploy domain %s → %s", deploy_domain, ip)
        return deploy_domain
    except Exception as exc:
        logger.warning("Failed to create deploy domain: %s", exc)
        return f"{deploy_domain} (DNS failed)"
