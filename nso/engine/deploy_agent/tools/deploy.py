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

# Platform workspace → systemd service mapping
_WORKSPACE_SERVICE_MAP = {
    "server": "nso",
    "agent": "nso-agent",
    "dashboard": "",
    "admin": "",
    "cli": "",
}


def _service_for_workspace(workspace: str, ws_data: dict | None = None) -> str:
    """Return the systemd service name for a workspace.

    Platform workspaces use a fixed map. User workspaces get 'nso-app' for
    python/node stacks, or empty string for static/custom.
    """
    if workspace in _WORKSPACE_SERVICE_MAP:
        return _WORKSPACE_SERVICE_MAP[workspace]
    # For user-created workspaces, infer from stack
    if ws_data:
        stack = ws_data.get("stack", "custom")
        if stack in ("static", "custom", ""):
            return ""  # static sites don't need a service restart
    return "nso-app"


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

    async def run_ship(workspace: str, instance_id: str = "", node_id: str = "",
                       branch: str = "main", domain: str = "") -> str:
        """Execute full ship pipeline: pack → push to R2 → deploy to node/instance."""
        try:
            target_id = node_id or instance_id
            return await _run_ship_impl(workspace, target_id, branch, domain)
        except Exception as exc:
            logger.exception("run_ship unhandled error for workspace=%s", workspace)
            return json.dumps({"error": f"Ship failed: {type(exc).__name__}: {exc}"})

    async def _resolve_deploy_target(ws: dict, target_id: str) -> tuple[str, str, int]:
        """Resolve deploy target to (target_id, ip, agent_port).

        Resolution order:
        1. Explicit target_id (node_* or inst_*)
        2. Workspace linked instance_id
        3. Config file deploy.instance_id
        4. Any online compute node
        5. Any running instance (legacy fallback)
        """
        from nso.engine.workspace.config import read_config

        ws_path = ws.get("path", "")

        # Step 1: Use explicit target if provided
        if not target_id:
            target_id = ws.get("instance_id", "")
        if not target_id and ws_path:
            config = read_config(ws_path)
            if config and config.deploy and config.deploy.instance_id:
                target_id = config.deploy.instance_id

        # Step 2: Validate the target
        if target_id:
            ip, port = await _resolve_target_ip(target_id)
            if ip:
                return target_id, ip, port
            logger.warning("Target %s not deployable, trying fallback", target_id)
            target_id = ""

        # Step 3: Fallback — try compute nodes first, then legacy instances
        nodes = await db.fetch_all("compute_nodes", project_id=ctx.project_id, status="online")
        for node in nodes:
            if node.get("ip"):
                return node["id"], node["ip"], node.get("agent_port", 8081)

        instances = await db.fetch_all("instances", project_id=ctx.project_id)
        running = [i for i in instances if i.get("state") in ("ready", "running") and i.get("ip")]
        if running:
            inst = running[0]
            return inst["id"], inst["ip"], 8081

        return "", "", 0

    async def _resolve_target_ip(target_id: str) -> tuple[str, int]:
        """Resolve a target_id (node_* or inst_*) to (ip, agent_port)."""
        if target_id.startswith("node_"):
            node = await db.fetch_one("compute_nodes", id=target_id)
            if node and node.get("ip") and node.get("project_id") == ctx.project_id:
                if node.get("status") in ("online", "provisioning"):
                    return node["ip"], node.get("agent_port", 8081)
            return "", 0

        # Legacy instance
        inst = await db.fetch_one("instances", id=target_id)
        if inst and inst.get("project_id") == ctx.project_id and inst.get("state") in ("ready", "running"):
            return inst.get("ip", ""), 8081
        return "", 0

    async def _run_ship_impl(workspace: str, target_id: str, branch: str, domain: str) -> str:
        from nso.engine.storage.zar_packer import pack
        from nso.engine.storage.service import R2Client
        from nso.engine.workspace.config import read_package_config

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path:
            return json.dumps({"error": "Workspace has no path"})

        # Auto-claim subdomain
        if ctx.user_id:
            await _auto_claim_subdomain(ctx.user_id)

        # Resolve deploy target (node or instance)
        target_id, target_ip, agent_port = await _resolve_deploy_target(ws, target_id)
        if not target_id or not target_ip:
            return json.dumps({"error": "No deploy target available. Create an instance or register a compute node first."})

        is_node = target_id.startswith("node_")

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

        # Deploy via agent — use target IP and port
        import httpx
        agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")

        agent_urls = [f"http://127.0.0.1:{agent_port}", f"http://{target_ip}:{agent_port}"]
        token = None
        last_error = None

        for agent_url in agent_urls:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{agent_url}/auth/login", json={
                        "email": settings.ADMIN_EMAIL,
                        "password": agent_password,
                    })
                if resp.status_code == 200:
                    token = resp.json()["token"]
                    break
                last_error = f"Agent auth failed (HTTP {resp.status_code})"
            except Exception as exc:
                last_error = str(exc)
                continue

        if not token:
            return json.dumps({"error": f"Cannot connect to agent: {last_error}"})

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

        # Update state — node or instance
        if is_node:
            prev_status = (await db.fetch_one("compute_nodes", id=target_id) or {}).get("status", "online")
        else:
            prev_state = (await db.fetch_one("instances", id=target_id) or {}).get("state", "running")
            await db.update("instances", target_id, {"state": "deploying", "workspace": workspace})

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{agent_url}/deploy/pull",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "r2_key": r2_key,
                        "r2_endpoint": r2_cfg.endpoint,
                        "r2_bucket": r2_cfg.bucket,
                        "r2_access_key_id": r2_cfg.access_key_id,
                        "r2_secret_access_key": r2_cfg.secret_access_key,
                        "target_dir": ws_path or "/opt/app",
                        "restart_service": _service_for_workspace(workspace, ws),
                        "install_deps": True,
                        "secrets": resolved_secrets,
                        "use_pipeline": True,
                    },
                )
            if resp.status_code != 200:
                if not is_node:
                    await db.update("instances", target_id, {"state": prev_state, "error": ""})
                return json.dumps({"error": f"Deploy failed: {resp.text[:500]}"})

            deploy_result = resp.json()
        except Exception as exc:
            if not is_node:
                await db.update("instances", target_id, {"state": prev_state, "error": ""})
            return json.dumps({"error": f"Deploy error: {exc}"})

        if not is_node:
            await db.update("instances", target_id, {"state": "running", "error": ""})

        # For domain assignment we need the instance_id (domains FK)
        instance_id_for_domain = target_id if not is_node else (
            (await db.fetch_one("compute_nodes", id=target_id) or {}).get("instance_id", target_id)
        )

        deploy_domain = await _auto_assign_domain(
            ctx.project_id, ctx.user_id, workspace,
            instance_id_for_domain, target_ip, domain,
        )

        # Auto-setup nginx + SSL on the agent for the deploy domain
        if deploy_domain and "(DNS failed)" not in deploy_domain:
            await _auto_setup_nginx(
                agent_url, token, deploy_domain, ws_path or "/opt/app", ws,
            )

        # Send deploy notification to user inbox
        if ctx.user_id:
            label = ""
            if is_node:
                label = ((await db.fetch_one("compute_nodes", id=target_id)) or {}).get("label", "")
            else:
                label = ((await db.fetch_one("instances", id=target_id)) or {}).get("label", "")
            await _send_deploy_notification(
                ctx.user_id, workspace, manifest.version, deploy_domain, label,
            )

        return json.dumps({
            "ok": True,
            "workspace": workspace,
            "version": manifest.version,
            "branch": branch,
            "r2_key": r2_key,
            "target_id": target_id,
            "domain": deploy_domain,
            "snapshot": deploy_result.get("snapshot", ""),
            "pipeline": deploy_result.get("pipeline", False),
        })

    async def check_deploy_status(target_id: str = "", instance_id: str = "", node_id: str = "") -> str:
        """Check the current deploy state on a node or instance."""
        tid = node_id or instance_id or target_id
        if not tid:
            return json.dumps({"error": "Provide target_id, instance_id, or node_id"})

        ip, agent_port = "", 8081

        if tid.startswith("node_"):
            node = await db.fetch_one("compute_nodes", id=tid)
            if not node or node.get("project_id") != ctx.project_id:
                return json.dumps({"error": f"Node {tid} not found"})
            ip = node.get("ip", "")
            agent_port = node.get("agent_port", 8081)
        else:
            inst = await db.fetch_one("instances", id=tid)
            if not inst or inst.get("project_id") != ctx.project_id:
                return json.dumps({"error": f"Instance {tid} not found"})
            ip = inst.get("ip", "")

        if not ip:
            return json.dumps({"error": "Target has no IP"})

        try:
            import httpx
            agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")
            for base_url in [f"http://127.0.0.1:{agent_port}", f"http://{ip}:{agent_port}"]:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.post(f"{base_url}/auth/login", json={
                            "email": settings.ADMIN_EMAIL, "password": agent_password,
                        })
                    if resp.status_code == 200:
                        token = resp.json()["token"]
                        async with httpx.AsyncClient(timeout=10) as client:
                            resp = await client.get(
                                f"{base_url}/deploy/current",
                                headers={"Authorization": f"Bearer {token}"},
                            )
                        if resp.status_code == 200:
                            return json.dumps(resp.json())
                        return json.dumps({"error": f"Status check failed: {resp.status_code}"})
                except Exception:
                    continue
            return json.dumps({"error": "Cannot reach agent on any address"})
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
        (check_deploy_status, "check_deploy_status", "Check deploy status on a node or instance"),
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
        owner_sub = (owner.get("subdomain") or "" if owner else "").strip()

        if owner_sub:
            deploy_domain = f"{workspace}-{owner_sub}.{settings.NSO_BASE_DOMAIN}"
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


async def _auto_setup_nginx(
    agent_url: str, token: str, domain: str, workspace_dir: str, ws: dict | None,
):
    """Tell the agent to set up nginx + SSL for the deploy domain."""
    import httpx

    # Determine if it's a static site or an app that needs proxying
    stack = ws.get("stack", "custom") if ws else "custom"
    port = 0  # static by default
    if stack in ("python", "node"):
        port = 3000  # default app port

    # Get existing cert domains to expand
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{agent_url}/exec/",
                headers={"Authorization": f"Bearer {token}"},
                json={"command": "openssl x509 -in /etc/letsencrypt/live/nso.dev/fullchain.pem -noout -text 2>&1 | grep -oP 'DNS:\\K[^,\\s]+'", "timeout": 5},
            )
        existing_domains = []
        if resp.status_code == 200:
            stdout = resp.json().get("stdout", "")
            existing_domains = [d.strip() for d in stdout.strip().splitlines() if d.strip()]
    except Exception:
        existing_domains = ["nso.dev"]

    # Add new domain if not already covered
    cert_domains = list(set(existing_domains + [domain]))

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{agent_url}/deploy/setup-domain",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "domain": domain,
                    "workspace_dir": workspace_dir,
                    "port": port,
                    "cert_name": "nso.dev",
                    "cert_domains": cert_domains,
                },
            )
        if resp.status_code == 200:
            result = resp.json()
            logger.info("Auto nginx setup: %s (ssl=%s)", domain, result.get("ssl_expanded"))
        else:
            logger.warning("Auto nginx setup failed for %s: %s", domain, resp.text[:300])
    except Exception as exc:
        logger.warning("Auto nginx setup error for %s: %s", domain, exc)


async def _send_deploy_notification(
    user_id: str, workspace: str, version: str, domain: str, instance_label: str,
):
    """Send an in-app notification after a successful deploy."""
    try:
        from nso.engine.notifications.routes import create_notification

        domain_line = f"\nDomain: https://{domain}" if domain and "(DNS failed)" not in domain else ""
        message = (
            f"Workspace '{workspace}' v{version} deployed successfully"
            f" to {instance_label}.{domain_line}"
        )

        await create_notification(
            user_id=user_id,
            title=f"Deploy: {workspace} shipped",
            message=message,
            notif_type="success",
        )
    except Exception as exc:
        logger.warning("Failed to send deploy notification: %s", exc)
