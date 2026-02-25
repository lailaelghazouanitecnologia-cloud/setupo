"""Deploy pipeline — detect stack, install deps, start app on instance.

Reads config.toml from the workspace when available to determine stack,
start command, port, and environment variables.
"""
import logging

from core import db
from core.errors import NotFoundError, ProviderError
from core.models import InstanceState, DeployState
from core.instances.provisioner import run_ssh_command
from core.deploy.sync import sync_workspace
from core.workspace_config import read_config
from server.config import settings

logger = logging.getLogger("mms.deploy")


async def _log(instance_id: str, message: str, level: str = "info"):
    """Add a deploy log entry."""
    await db.insert("deploy_logs", {
        "instance_id": instance_id,
        "level": level,
        "message": message,
    })
    logger.info("[deploy %s] %s", instance_id, message)


async def deploy_to_instance(
    project_id: str,
    instance_id: str,
    workspace_name: str,
    branch: str = "main",
    command: str | None = None,
) -> dict:
    """Full deploy pipeline: sync → detect → install → start.

    Reads config.toml from the workspace for stack/command/port/env overrides.
    Returns deploy status dict.
    """
    # Validate instance
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst or inst["project_id"] != project_id:
        raise NotFoundError("Instance", instance_id)
    if inst["state"] not in (InstanceState.READY.value, InstanceState.RUNNING.value):
        raise ProviderError("deploy", f"Instance is in state '{inst['state']}', must be 'ready' or 'running'")

    ip = inst.get("ip")
    if not ip:
        raise ProviderError("deploy", "Instance has no IP")

    # Validate workspace
    ws = await db.fetch_one("workspaces", project_id=project_id, name=workspace_name)
    if not ws:
        raise NotFoundError("Workspace", workspace_name)

    # Read config.toml for deploy settings
    ws_config = read_config(ws["path"])
    config_stack = ws_config.type if ws_config else None
    config_command = ws_config.deploy.command if ws_config else None
    config_port = ws_config.deploy.port if ws_config else 3000
    config_env = ws_config.deploy.env if ws_config else {}
    config_domain = None
    if ws_config and ws_config.services.get("nginx"):
        config_domain = ws_config.services["nginx"].domain

    keys_dir = settings.keys_dir(project_id)
    key_path = str(keys_dir / "id_ed25519")
    remote_dir = "/opt/app"

    # Update state
    await db.update("instances", instance_id, {
        "state": InstanceState.DEPLOYING.value,
        "workspace": workspace_name,
    })

    try:
        # 1. Sync files
        await _log(instance_id, f"Syncing workspace '{workspace_name}' to {ip}:{remote_dir}")
        ok, sync_output = await sync_workspace(ws["path"], ip, key_path, remote_dir)
        if not ok:
            raise ProviderError("deploy", f"File sync failed: {sync_output}")
        await _log(instance_id, "Files synced successfully")

        # 2. Detect stack (config.toml overrides auto-detection)
        if config_stack and config_stack != "custom":
            stack = config_stack
            await _log(instance_id, f"Stack from config.toml: {stack}")
        else:
            await _log(instance_id, "Detecting project stack...")
            stack = await _detect_stack(ip, key_path, remote_dir)
            await _log(instance_id, f"Detected stack: {stack}")

        # 3. Install dependencies
        await _log(instance_id, "Installing dependencies...")
        await _install_deps(ip, key_path, remote_dir, stack)
        await _log(instance_id, "Dependencies installed")

        # 4. Set env vars on instance if config.toml has them
        if config_env:
            await _log(instance_id, f"Setting {len(config_env)} env vars from config.toml")
            env_lines = "\n".join(f"{k}={v}" for k, v in config_env.items())
            await run_ssh_command(ip, f"cat >> {remote_dir}/.env << 'ENVEOF'\n{env_lines}\nENVEOF", key_path)

        # 5. Start application
        start_cmd = command or config_command or _default_start_command(stack)
        await _log(instance_id, f"Starting app: {start_cmd}")
        port = config_port or 3000
        await _start_app(ip, key_path, remote_dir, start_cmd, port=port, env_vars=config_env)

        # 6. Configure nginx reverse proxy for the user app
        domain = config_domain or inst.get("domain")
        await _log(instance_id, "Configuring nginx for app...")
        await _setup_app_nginx(ip, key_path, domain, stack, port=port)

        # 6. Setup SSL if domain is configured
        if domain:
            await _log(instance_id, f"Setting up SSL for {domain}...")
            from core.instances.provisioner import setup_ssl
            ssl_out, ssl_code = await setup_ssl(ip, domain, key_path)
            if ssl_code == 0:
                await _log(instance_id, f"SSL configured for {domain}")
            else:
                await _log(instance_id, f"SSL setup failed (non-fatal): {ssl_out[:200]}", level="warning")

        await db.update("instances", instance_id, {
            "state": InstanceState.RUNNING.value,
        })
        await _log(instance_id, "Deploy complete — app is running")

        return {
            "state": DeployState.LIVE.value,
            "instance_id": instance_id,
            "workspace": workspace_name,
            "stack": stack,
            "url": f"https://{domain}" if domain else f"http://{ip}",
        }

    except Exception as e:
        await _log(instance_id, f"Deploy failed: {e}", level="error")
        await db.update("instances", instance_id, {
            "state": InstanceState.ERROR.value,
            "error": str(e),
        })
        return {
            "state": DeployState.FAILED.value,
            "instance_id": instance_id,
            "error": str(e),
        }


async def _detect_stack(ip: str, key_path: str, remote_dir: str) -> str:
    """Detect the project stack by checking for config files."""
    checks = [
        ("package.json", "node"),
        ("requirements.txt", "python"),
        ("Pipfile", "python"),
        ("pyproject.toml", "python"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
        ("Dockerfile", "docker"),
        ("docker-compose.yml", "docker"),
        ("index.html", "static"),
    ]
    for filename, stack in checks:
        output, code = await run_ssh_command(ip, f"test -f {remote_dir}/{filename} && echo yes", key_path)
        if code == 0 and "yes" in output:
            return stack
    return "unknown"


async def _install_deps(ip: str, key_path: str, remote_dir: str, stack: str):
    """Install dependencies based on detected stack."""
    commands = {
        "node": f"cd {remote_dir} && npm install --production 2>&1",
        "python": f"cd {remote_dir} && pip install -r requirements.txt 2>&1",
        "go": f"cd {remote_dir} && go build ./... 2>&1",
        "rust": f"cd {remote_dir} && cargo build --release 2>&1",
        "docker": f"cd {remote_dir} && docker compose up -d --build 2>&1",
        "static": "echo 'No deps for static site'",
    }
    cmd = commands.get(stack)
    if cmd:
        output, code = await run_ssh_command(ip, cmd, key_path, timeout=300)
        if code != 0:
            raise ProviderError("deploy", f"Dependency install failed (exit {code}): {output[-500:]}")


def _default_start_command(stack: str) -> str:
    """Default start command based on stack."""
    return {
        "node": "npm start",
        "python": "python main.py",
        "go": "./main",
        "rust": "./target/release/*",
        "docker": "docker compose up -d",
        "static": "echo 'Static site served by nginx'",
    }.get(stack, "echo 'Unknown stack'")


async def _setup_app_nginx(ip: str, key_path: str, domain: str | None, stack: str, port: int = 3000):
    """Configure nginx on the instance to reverse-proxy the user's app."""
    server_name = domain or "_"
    if stack == "static":
        location_block = """
        location / {
            root /opt/app;
            index index.html;
            try_files $uri $uri/ /index.html;
        }"""
    else:
        location_block = f"""
        location / {{
            proxy_pass http://127.0.0.1:{port};
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }}"""

    nginx_conf = f"""server {{
    listen 80;
    server_name {server_name};
{location_block}
}}
"""
    write_cmd = f"cat > /etc/nginx/sites-available/app << 'NGINXEOF'\n{nginx_conf}\nNGINXEOF"
    await run_ssh_command(ip, write_cmd, key_path)
    await run_ssh_command(ip, "ln -sf /etc/nginx/sites-available/app /etc/nginx/sites-enabled/app", key_path)
    await run_ssh_command(ip, "nginx -t && systemctl reload nginx", key_path)


async def _start_app(ip: str, key_path: str, remote_dir: str, command: str, port: int = 3000, env_vars: dict | None = None):
    """Start the app as a background process via systemd."""
    env_lines = [
        f"Environment=NODE_ENV=production",
        f"Environment=PORT={port}",
    ]
    for k, v in (env_vars or {}).items():
        env_lines.append(f"Environment={k}={v}")
    env_block = "\n".join(env_lines)

    service = f"""[Unit]
Description=MMS App
After=network.target

[Service]
Type=simple
WorkingDirectory={remote_dir}
ExecStart=/bin/bash -c '{command}'
Restart=on-failure
RestartSec=5
{env_block}

[Install]
WantedBy=multi-user.target
"""
    # Write service file and start
    write_cmd = f"cat > /etc/systemd/system/mms-app.service << 'SERVICEEOF'\n{service}\nSERVICEEOF"
    await run_ssh_command(ip, write_cmd, key_path)
    await run_ssh_command(ip, "systemctl daemon-reload && systemctl enable mms-app && systemctl restart mms-app", key_path)


async def get_deploy_logs(instance_id: str, limit: int = 100) -> list[dict]:
    """Get deploy logs for an instance."""
    database = await db.get_db()
    cursor = await database.execute(
        "SELECT * FROM deploy_logs WHERE instance_id = ? ORDER BY id DESC LIMIT ?",
        (instance_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
