"""
Deploy Agent tools — functions the AI agent can call during deploy chat.

Tools:
  - analyze_project: Scan workspace files and detect stack, structure, entry points
  - generate_deploy_config: Generate deploy.toml based on analysis
  - list_workspaces: List project workspaces
  - list_instances: List project instances
  - run_build: Trigger build for workspace
  - run_ship: Execute full ship (pack + push + deploy)
  - claim_subdomain: Auto-claim subdomain for user if not claimed
  - check_deploy_status: Check current deploy state on instance
  - read_workspace_file: Read a file from workspace
  - write_workspace_file: Write a file to workspace
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nso.shared import db
from nso.config import settings

logger = logging.getLogger("nso.deploy_agent.tools")


# ── Context passed to all tools ──

class DeployContext:
    """Shared context for all tool calls within a deploy session."""

    def __init__(self, project_id: str, user_id: str = ""):
        self.project_id = project_id
        self.user_id = user_id


def create_tools(ctx: DeployContext) -> list[tuple]:
    """Create all deploy tools bound to a project context.

    Returns list of (callable, name, description) tuples.
    """

    async def analyze_project(workspace: str = "") -> str:
        """Analyze a workspace or the entire project to detect stack, structure, dependencies, and entry points. Call this first before deploying."""
        if workspace:
            ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
            if not ws:
                return json.dumps({"error": f"Workspace '{workspace}' not found"})
            ws_path = ws.get("path", "")
            if not ws_path or not os.path.isdir(ws_path):
                return json.dumps({"error": f"Workspace path not found: {ws_path}"})
            return json.dumps(_analyze_directory(ws_path, workspace))
        else:
            # Analyze all workspaces
            workspaces = await db.fetch_all("workspaces", project_id=ctx.project_id)
            if not workspaces:
                return json.dumps({"workspaces": [], "hint": "No workspaces found. Create one first."})
            results = []
            for ws in workspaces:
                ws_path = ws.get("path", "")
                if ws_path and os.path.isdir(ws_path):
                    results.append(_analyze_directory(ws_path, ws.get("name", "")))
                else:
                    results.append({"name": ws.get("name", ""), "error": "path not found"})
            return json.dumps({"workspaces": results})

    async def generate_deploy_config(workspace: str, analysis: str = "") -> str:
        """Generate a deploy.toml configuration file for a workspace based on its analysis. The analysis parameter should contain the output from analyze_project."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path:
            return json.dumps({"error": "Workspace has no path"})

        # Auto-analyze if not provided
        if not analysis:
            info = _analyze_directory(ws_path, workspace)
        else:
            try:
                info = json.loads(analysis)
            except Exception:
                info = _analyze_directory(ws_path, workspace)

        deploy_toml = _generate_deploy_toml(info)
        deploy_path = os.path.join(ws_path, "deploy.toml")
        Path(deploy_path).write_text(deploy_toml)

        return json.dumps({
            "ok": True,
            "path": deploy_path,
            "content": deploy_toml,
            "message": f"deploy.toml written to {deploy_path}",
        })

    async def list_workspaces() -> str:
        """List all workspaces in the project with their configuration."""
        workspaces = await db.fetch_all("workspaces", project_id=ctx.project_id)
        result = []
        for ws in workspaces:
            result.append({
                "name": ws.get("name", ""),
                "path": ws.get("path", ""),
                "instance_id": ws.get("instance_id", ""),
                "created_at": ws.get("created_at", ""),
            })
        return json.dumps({"workspaces": result})

    async def list_instances() -> str:
        """List all VPS instances in the project with their state and IP."""
        instances = await db.fetch_all("instances", project_id=ctx.project_id)
        result = []
        for inst in instances:
            result.append({
                "id": inst.get("id", ""),
                "label": inst.get("label", ""),
                "ip": inst.get("ip", ""),
                "state": inst.get("state", ""),
                "region": inst.get("region", ""),
                "plan": inst.get("plan", ""),
                "workspace": inst.get("workspace", ""),
            })
        return json.dumps({"instances": result})

    async def run_build(workspace: str, build_command: str = "") -> str:
        """Trigger a build for a workspace. Uses the smart build system (cache, server, or agent)."""
        from nso.engine.build.service import execute_build, compute_source_hash
        from nso.engine.storage.zar_packer import pack
        from nso.engine.workspace.config import read_config, read_package_config

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
        """Execute the full ship pipeline: pack workspace → push to R2 → deploy to instance. This also auto-claims subdomain if not claimed."""
        from nso.engine.storage.zar_packer import pack
        from nso.engine.storage.service import R2Client
        from nso.engine.workspace.config import read_config, read_package_config

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path:
            return json.dumps({"error": "Workspace has no path"})

        # Auto-claim subdomain before deploy
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
                    # Find any ready instance
                    instances = await db.fetch_all("instances", project_id=ctx.project_id)
                    ready = [i for i in instances if i.get("state") in ("ready", "running")]
                    if ready:
                        instance_id = ready[0]["id"]
                    else:
                        return json.dumps({"error": "No instance available. Create one first."})

        # Check instance
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

        # Auto-assign domain
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

    async def read_workspace_file(workspace: str, file_path: str) -> str:
        """Read a file from a workspace directory. Use this to inspect config files, package.json, etc."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        full = os.path.join(ws_path, file_path)

        # Safety: prevent traversal
        if ".." in file_path or not os.path.abspath(full).startswith(os.path.abspath(ws_path)):
            return json.dumps({"error": "Path traversal not allowed"})

        if not os.path.isfile(full):
            return json.dumps({"error": f"File not found: {file_path}"})

        try:
            content = Path(full).read_text()
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            return json.dumps({"path": file_path, "content": content})
        except Exception as e:
            return json.dumps({"error": f"Cannot read file: {e}"})

    async def write_workspace_file(workspace: str, file_path: str, content: str) -> str:
        """Write a file to a workspace directory. Use this to create or update deploy.toml, config files, etc."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        full = os.path.join(ws_path, file_path)

        if ".." in file_path or not os.path.abspath(full).startswith(os.path.abspath(ws_path)):
            return json.dumps({"error": "Path traversal not allowed"})

        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            Path(full).write_text(content)
            return json.dumps({"ok": True, "path": file_path, "size": len(content)})
        except Exception as e:
            return json.dumps({"error": f"Cannot write file: {e}"})

    async def run_validation(workspace: str = "", checks: str = "") -> str:
        """Run validation checks on a workspace. If validate.toml exists in the workspace it runs those checks. Otherwise you can pass inline checks as a JSON array like: [{"name":"health","type":"http","url":"https://domain/health","expect_status":200}]"""
        from nso.engine.validator import service as validator_service

        # Build context
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

                # Try domain lookup
                domains = await db.fetch_all("domains", project_id=ctx.project_id)
                for dom in domains:
                    if workspace in dom.get("domain", ""):
                        context["domain"] = dom["domain"]
                        break

                # Try validate.toml
                toml_path = os.path.join(ws_path, "validate.toml") if ws_path else ""
                if toml_path and os.path.isfile(toml_path):
                    try:
                        content = Path(toml_path).read_text()
                        validations = validator_service.parse_validate_toml(content, ctx.project_id)
                    except Exception as e:
                        return json.dumps({"error": f"Invalid validate.toml: {e}"})

        # Inline checks override
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

    # ── Connector management tools ──

    async def setup_connector(connector_id: str, config_json: str) -> str:
        """Install and configure a connector (github, s3, slack) with credentials.

        The config_json must be a JSON object with the required fields:
        - github: {"token": "ghp_xxx"}
        - s3: {"endpoint": "https://...", "access_key": "...", "secret_key": "...", "bucket": "..."}
        - slack: {"bot_token": "xoxb-xxx"} or {"webhook_url": "https://hooks.slack.com/..."}

        This will install the connector if not already installed, update its config,
        sync credentials to project secrets, and test the connection.
        """
        try:
            config = json.loads(config_json) if isinstance(config_json, str) else config_json
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON for config"})

        valid_connectors = {"github", "s3", "slack"}
        if connector_id not in valid_connectors:
            return json.dumps({"error": f"Unknown connector: {connector_id}. Valid: {', '.join(valid_connectors)}"})

        # Check if installed
        existing = await db.fetch_one("addons", project_id=ctx.project_id, addon_id=connector_id, addon_type="connector")

        if not existing:
            # Install it
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
            # Update config (merge)
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
        (analyze_project, "analyze_project", "Analyze workspace to detect stack, files, dependencies, entry points"),
        (generate_deploy_config, "generate_deploy_config", "Generate deploy.toml from analysis"),
        (list_workspaces, "list_workspaces", "List all workspaces in the project"),
        (list_instances, "list_instances", "List all VPS instances in the project"),
        (run_build, "run_build", "Trigger smart build for a workspace"),
        (run_ship, "run_ship", "Execute full ship: pack + push + deploy + auto-domain"),
        (check_deploy_status, "check_deploy_status", "Check deploy status on an instance"),
        (read_workspace_file, "read_workspace_file", "Read a file from workspace"),
        (write_workspace_file, "write_workspace_file", "Write a file to workspace"),
        (run_validation, "run_validation", "Run validation checks on a workspace (from validate.toml or inline)"),
        (setup_connector, "setup_connector", "Install and configure a connector (github, s3, slack) with credentials — auto-tests connection"),
        (list_connectors, "list_connectors", "List installed connectors with their connection status"),
    ]


# ── Internal helpers ──

def _analyze_directory(ws_path: str, name: str) -> dict:
    """Scan a workspace directory and return structured analysis."""
    info: dict = {"name": name, "path": ws_path, "files": [], "stack": "unknown", "entry_points": []}

    if not os.path.isdir(ws_path):
        info["error"] = "Directory not found"
        return info

    # Collect top-level files (max 100)
    all_files = []
    for entry in sorted(os.listdir(ws_path))[:100]:
        full = os.path.join(ws_path, entry)
        if entry.startswith(".") or entry in ("node_modules", "__pycache__", "venv", ".venv", ".git"):
            continue
        is_dir = os.path.isdir(full)
        size = os.path.getsize(full) if not is_dir else 0
        all_files.append({"name": entry, "is_dir": is_dir, "size": size})
    info["files"] = all_files

    # Stack detection
    stack_indicators = [
        ("package.json", "node"),
        ("requirements.txt", "python"),
        ("pyproject.toml", "python"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
        ("Dockerfile", "docker"),
        ("docker-compose.yml", "docker"),
        ("index.html", "static"),
        ("Gemfile", "ruby"),
    ]
    for filename, stack in stack_indicators:
        if os.path.exists(os.path.join(ws_path, filename)):
            info["stack"] = stack
            break

    # Framework detection for node
    pkg_path = os.path.join(ws_path, "package.json")
    if os.path.isfile(pkg_path):
        try:
            with open(pkg_path) as f:
                pkg = json.load(f)
            info["package_name"] = pkg.get("name", "")
            info["package_version"] = pkg.get("version", "")
            info["scripts"] = list(pkg.get("scripts", {}).keys())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                info["framework"] = "nextjs"
            elif "nuxt" in deps:
                info["framework"] = "nuxt"
            elif "vite" in deps:
                info["framework"] = "vite"
            elif "react" in deps:
                info["framework"] = "react"
            elif "vue" in deps:
                info["framework"] = "vue"
            elif "express" in deps:
                info["framework"] = "express"
            elif "fastify" in deps:
                info["framework"] = "fastify"
            info["has_build"] = "build" in pkg.get("scripts", {})
            info["has_start"] = "start" in pkg.get("scripts", {})
            info["has_dev"] = "dev" in pkg.get("scripts", {})
        except Exception:
            pass

    # Python analysis
    req_path = os.path.join(ws_path, "requirements.txt")
    if os.path.isfile(req_path):
        try:
            reqs = Path(req_path).read_text().strip().splitlines()
            info["python_deps"] = [r.strip() for r in reqs if r.strip() and not r.startswith("#")][:20]
            for dep in info["python_deps"]:
                dep_lower = dep.lower().split("==")[0].split(">=")[0]
                if dep_lower == "fastapi":
                    info["framework"] = "fastapi"
                elif dep_lower == "django":
                    info["framework"] = "django"
                elif dep_lower == "flask":
                    info["framework"] = "flask"
        except Exception:
            pass

    # Entry points
    entry_candidates = [
        "main.py", "app.py", "server.py", "index.py", "manage.py",
        "server.js", "index.js", "app.js", "main.js",
        "server.ts", "index.ts", "app.ts", "main.ts",
        "main.go", "cmd/main.go",
    ]
    for ep in entry_candidates:
        if os.path.isfile(os.path.join(ws_path, ep)):
            info["entry_points"].append(ep)

    # deploy.toml exists?
    info["has_deploy_toml"] = os.path.isfile(os.path.join(ws_path, "deploy.toml"))
    info["has_config_toml"] = os.path.isfile(os.path.join(ws_path, "config.toml"))
    info["has_dockerfile"] = os.path.isfile(os.path.join(ws_path, "Dockerfile"))

    return info


def _generate_deploy_toml(info: dict) -> str:
    """Generate a deploy.toml based on project analysis."""
    stack = info.get("stack", "unknown")
    framework = info.get("framework", "")
    name = info.get("name", "app")

    lines = [
        f'# Deploy configuration for {name}',
        f'# Auto-generated by NSO deploy agent',
        '',
        '[workspace]',
        f'name = "{name}"',
        '',
    ]

    # Install section
    if stack == "node":
        lines += ['[install]', 'command = "npm install"', 'timeout = 300', '']
    elif stack == "python":
        lines += ['[install]', 'command = "pip install -r requirements.txt"', 'timeout = 300', '']
    elif stack == "go":
        lines += ['[install]', 'command = "go mod download"', 'timeout = 120', '']
    elif stack == "rust":
        lines += ['[install]', 'command = "cargo fetch"', 'timeout = 120', '']

    # Build section
    if info.get("has_build"):
        if framework == "nextjs":
            lines += ['[build]', 'command = "npm run build"', 'timeout = 600', '', '[build.env]', 'NODE_ENV = "production"', '']
        elif framework == "vite":
            lines += ['[build]', 'command = "npm run build"', 'timeout = 300', '', '[build.env]', 'NODE_ENV = "production"', '']
        elif framework in ("react", "vue", "nuxt"):
            lines += ['[build]', 'command = "npm run build"', 'timeout = 600', '']
    elif stack == "go":
        lines += ['[build]', 'command = "go build -o app ./..."', 'timeout = 300', '']
    elif stack == "rust":
        lines += ['[build]', 'command = "cargo build --release"', 'timeout = 600', '']

    # Services section
    if framework in ("express", "fastify") or (stack == "node" and info.get("has_start")):
        lines += [
            '[services.app]',
            'command = "npm start"',
            'port = 3000',
            'user = "root"',
            '',
        ]
    elif framework == "nextjs":
        lines += [
            '[services.app]',
            'command = "npm start"',
            'port = 3000',
            'user = "root"',
            '',
        ]
    elif framework == "fastapi":
        entry = info.get("entry_points", ["main.py"])[0].replace(".py", "")
        lines += [
            '[services.app]',
            f'command = "uvicorn {entry}:app --host 0.0.0.0 --port 8000"',
            'port = 8000',
            'user = "root"',
            '',
        ]
    elif framework == "django":
        lines += [
            '[services.app]',
            'command = "gunicorn --bind 0.0.0.0:8000 --workers 2 app.wsgi"',
            'port = 8000',
            'user = "root"',
            '',
        ]
    elif framework == "flask":
        entry = info.get("entry_points", ["app.py"])[0].replace(".py", "")
        lines += [
            '[services.app]',
            f'command = "gunicorn --bind 0.0.0.0:8000 {entry}:app"',
            'port = 8000',
            'user = "root"',
            '',
        ]
    elif stack == "go":
        lines += [
            '[services.app]',
            'command = "./app"',
            'port = 8080',
            'user = "root"',
            '',
        ]
    elif stack == "static":
        lines += [
            '# Static site — served directly by nginx',
            '',
        ]

    # Health check
    if stack != "static":
        port = "3000" if stack == "node" else "8000"
        lines += [
            '[health]',
            'strategy = "http"',
            f'url = "http://localhost:{port}/"',
            'timeout = 30',
            'retries = 5',
            '',
        ]

    return "\n".join(lines) + "\n"


def _detect_build_cmd(ws_path: str) -> str:
    """Auto-detect build command."""
    checks = [
        ("package.json", "npm run build"),
        ("Makefile", "make build"),
        ("Cargo.toml", "cargo build --release"),
        ("go.mod", "go build -o app ./..."),
    ]
    for filename, cmd in checks:
        fpath = os.path.join(ws_path, filename)
        if not os.path.exists(fpath):
            continue
        if filename == "package.json":
            try:
                with open(fpath) as f:
                    pkg = json.load(f)
                if "build" not in pkg.get("scripts", {}):
                    continue
            except Exception:
                continue
        return cmd
    return ""


async def _auto_claim_subdomain(user_id: str):
    """Auto-claim a subdomain for the user if they don't have one.

    Uses the user's name or email prefix as the subdomain.
    """
    user = await db.fetch_one("users", id=user_id)
    if not user:
        return
    if user.get("subdomain"):
        return  # already claimed

    # Generate subdomain from name or email
    import re
    name = user.get("name", "") or user.get("email", "").split("@")[0]
    sub = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    if len(sub) < 3:
        sub = f"user-{user_id[-8:]}"
    sub = sub[:32]

    # Check availability
    from nso.engine.auth import service as auth_service
    try:
        available = await auth_service.check_subdomain_available(sub)
        if not available:
            sub = f"{sub}-{user_id[-4:]}"
            available = await auth_service.check_subdomain_available(sub)
        if not available:
            return  # give up

        await auth_service.claim_subdomain(user_id, sub)

        # Create DNS CNAME
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
        # Use owner subdomain
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

        # Store in domains table
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
