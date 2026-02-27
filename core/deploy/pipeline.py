import logging

from core import db
from core.errors import NotFoundError, ProviderError
from core.models import InstanceState, DeployState
from core.instances.provisioner import run_ssh_command
from core.deploy.sync import sync_workspace
from core.workspace_config import read_config
from server.config import settings

logger = logging.getLogger("setupo.deploy")


DEPS_INSTALL_TIMEOUT = 300
REMOTE_APP_DIR = "/opt/app"
DEFAULT_PORT = 3000

STACK_CHECKS = [
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

INSTALL_COMMANDS = {
    "node": "npm install --production 2>&1",
    "python": "pip install -r requirements.txt 2>&1",
    "go": "go build ./... 2>&1",
    "rust": "cargo build --release 2>&1",
    "docker": "docker compose up -d --build 2>&1",
    "static": "echo 'No deps for static site'",
}

DEFAULT_START_COMMANDS = {
    "node": "npm start",
    "python": "python main.py",
    "go": "./main",
    "rust": "./target/release/*",
    "docker": "docker compose up -d",
    "static": "echo 'Static site served by nginx'",
}


async def _log(instance_id: str, message: str, level: str = "info"):
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
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst or inst["project_id"] != project_id:
        raise NotFoundError("Instance", instance_id)
    if inst["state"] not in (InstanceState.READY.value, InstanceState.RUNNING.value):
        raise ProviderError("deploy", f"Instance is in state '{inst['state']}', must be 'ready' or 'running'")

    ip = inst.get("ip")
    if not ip:
        raise ProviderError("deploy", "Instance has no IP")

    ws = await db.fetch_one("workspaces", project_id=project_id, name=workspace_name)
    if not ws:
        raise NotFoundError("Workspace", workspace_name)

    ws_config = read_config(ws["path"])
    config_stack = ws_config.type if ws_config else None
    config_command = ws_config.deploy.command if ws_config else None
    config_port = ws_config.deploy.port if ws_config else DEFAULT_PORT
    config_env = ws_config.deploy.env if ws_config else {}
    config_domain = None
    if ws_config and ws_config.services.get("nginx"):
        config_domain = ws_config.services["nginx"].domain

    keys_dir = settings.keys_dir(project_id)
    key_path = str(keys_dir / "id_ed25519")
    remote_dir = REMOTE_APP_DIR

    await db.update("instances", instance_id, {
        "state": InstanceState.DEPLOYING.value,
        "workspace": workspace_name,
    })

    try:
        await _log(instance_id, f"Syncing workspace '{workspace_name}' to {ip}:{remote_dir}")
        ok, sync_output = await sync_workspace(ws["path"], ip, key_path, remote_dir)
        if not ok:
            raise ProviderError("deploy", f"File sync failed: {sync_output}")
        await _log(instance_id, "Files synced successfully")

        if config_stack and config_stack != "custom":
            stack = config_stack
            await _log(instance_id, f"Stack from config.toml: {stack}")
        else:
            await _log(instance_id, "Detecting project stack...")
            stack = await _detect_stack(ip, key_path, remote_dir)
            await _log(instance_id, f"Detected stack: {stack}")

        await _log(instance_id, "Installing dependencies...")
        await _install_deps(ip, key_path, remote_dir, stack)
        await _log(instance_id, "Dependencies installed")

        if config_env:
            await _log(instance_id, f"Setting {len(config_env)} env vars from config.toml")
            env_lines = "\n".join(f"{k}={v}" for k, v in config_env.items())
            await run_ssh_command(ip, f"cat >> {remote_dir}/.env << 'ENVEOF'\n{env_lines}\nENVEOF", key_path)

        start_cmd = command or config_command or _default_start_command(stack)
        await _log(instance_id, f"Starting app: {start_cmd}")
        port = config_port or DEFAULT_PORT
        await _start_app(ip, key_path, remote_dir, start_cmd, port=port, env_vars=config_env)

        domain = config_domain or inst.get("domain")
        await _log(instance_id, "Configuring nginx for app...")
        await _setup_app_nginx(ip, key_path, domain, stack, port=port)

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
    for filename, stack in STACK_CHECKS:
        output, code = await run_ssh_command(ip, f"test -f {remote_dir}/{filename} && echo yes", key_path)
        if code == 0 and "yes" in output:
            return stack
    return "unknown"


async def _install_deps(ip: str, key_path: str, remote_dir: str, stack: str):
    base_cmd = INSTALL_COMMANDS.get(stack)
    if not base_cmd:
        return
    cmd = f"cd {remote_dir} && {base_cmd}" if stack != "static" else base_cmd
    output, code = await run_ssh_command(ip, cmd, key_path, timeout=DEPS_INSTALL_TIMEOUT)
    if code != 0:
        raise ProviderError("deploy", f"Dependency install failed (exit {code}): {output[-500:]}")


def _default_start_command(stack: str) -> str:
    return DEFAULT_START_COMMANDS.get(stack, "echo 'Unknown stack'")


async def _setup_app_nginx(ip: str, key_path: str, domain: str | None, stack: str, port: int = DEFAULT_PORT):
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


async def _start_app(ip: str, key_path: str, remote_dir: str, command: str, port: int = DEFAULT_PORT, env_vars: dict | None = None):
    env_lines = [
        f"Environment=NODE_ENV=production",
        f"Environment=PORT={port}",
    ]
    for k, v in (env_vars or {}).items():
        env_lines.append(f"Environment={k}={v}")
    env_block = "\n".join(env_lines)

    service = f"""[Unit]
Description=Setupo App
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
    write_cmd = f"cat > /etc/systemd/system/setupo-app.service << 'SERVICEEOF'\n{service}\nSERVICEEOF"
    await run_ssh_command(ip, write_cmd, key_path)
    await run_ssh_command(ip, "systemctl daemon-reload && systemctl enable setupo-app && systemctl restart setupo-app", key_path)


LOG_FETCH_LIMIT = 100


async def get_deploy_logs(instance_id: str, limit: int = LOG_FETCH_LIMIT) -> list[dict]:
    database = await db.get_db()
    cursor = await database.execute(
        "SELECT * FROM deploy_logs WHERE instance_id = ? ORDER BY id DESC LIMIT ?",
        (instance_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
