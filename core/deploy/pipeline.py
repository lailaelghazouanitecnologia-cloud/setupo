"""Deploy pipeline — detect stack, install deps, start app on instance."""
import logging

from core import db
from core.errors import NotFoundError, ProviderError
from core.models import InstanceState, DeployState
from core.instances.provisioner import run_ssh_command
from core.deploy.sync import sync_workspace
from server.config import settings

logger = logging.getLogger("setupo.deploy")


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

        # 2. Detect stack
        await _log(instance_id, "Detecting project stack...")
        stack = await _detect_stack(ip, key_path, remote_dir)
        await _log(instance_id, f"Detected stack: {stack}")

        # 3. Install dependencies
        await _log(instance_id, "Installing dependencies...")
        await _install_deps(ip, key_path, remote_dir, stack)
        await _log(instance_id, "Dependencies installed")

        # 4. Start application
        start_cmd = command or _default_start_command(stack)
        await _log(instance_id, f"Starting app: {start_cmd}")
        await _start_app(ip, key_path, remote_dir, start_cmd)

        # 5. Setup domain if configured
        domain = inst.get("domain")
        if domain:
            await _log(instance_id, f"Domain configured: {domain}")

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


async def _start_app(ip: str, key_path: str, remote_dir: str, command: str):
    """Start the app as a background process via systemd or nohup."""
    # Create a simple systemd service
    service = f"""[Unit]
Description=Setupo App
After=network.target

[Service]
Type=simple
WorkingDirectory={remote_dir}
ExecStart=/bin/bash -c '{command}'
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production
Environment=PORT=3000

[Install]
WantedBy=multi-user.target
"""
    # Write service file and start
    write_cmd = f"cat > /etc/systemd/system/setupo-app.service << 'SERVICEEOF'\n{service}\nSERVICEEOF"
    await run_ssh_command(ip, write_cmd, key_path)
    await run_ssh_command(ip, "systemctl daemon-reload && systemctl enable setupo-app && systemctl restart setupo-app", key_path)


async def get_deploy_logs(instance_id: str, limit: int = 100) -> list[dict]:
    """Get deploy logs for an instance."""
    database = await db.get_db()
    cursor = await database.execute(
        "SELECT * FROM deploy_logs WHERE instance_id = ? ORDER BY id DESC LIMIT ?",
        (instance_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
