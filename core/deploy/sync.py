"""Workspace sync — upload workspace files to an instance via rsync/scp."""
import asyncio
import logging

from core.instances.provisioner import scp_upload, run_ssh_command

logger = logging.getLogger("setupo.deploy.sync")


async def sync_workspace(
    workspace_path: str,
    ip: str,
    key_path: str,
    remote_dir: str = "/opt/app",
    user: str = "root",
) -> tuple[bool, str]:
    """Sync a local workspace directory to the remote instance.

    Tries rsync first (faster, incremental), falls back to scp.
    """
    # Ensure remote dir exists
    await run_ssh_command(ip, f"mkdir -p {remote_dir}", key_path, user=user)

    # Try rsync
    ssh_opts = (
        f"-e 'ssh -i {key_path} "
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o LogLevel=ERROR'"
    )
    rsync_cmd = (
        f"rsync -avz --delete "
        f"--exclude '.git' --exclude 'node_modules' --exclude '__pycache__' "
        f"--exclude '.env' --exclude 'venv' --exclude '.venv' "
        f"{ssh_opts} "
        f"{workspace_path}/ {user}@{ip}:{remote_dir}/"
    )

    try:
        proc = await asyncio.create_subprocess_shell(
            rsync_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        output = stdout.decode(errors="replace")

        if proc.returncode == 0:
            logger.info("rsync to %s:%s successful", ip, remote_dir)
            return True, output
        else:
            logger.warning("rsync failed (code %d), falling back to scp", proc.returncode)
    except Exception as e:
        logger.warning("rsync failed: %s, falling back to scp", e)

    # Fallback to scp
    ok = await scp_upload(ip, workspace_path, remote_dir, key_path, user=user)
    return ok, "scp upload " + ("succeeded" if ok else "failed")
