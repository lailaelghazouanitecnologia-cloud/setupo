"""Instance provisioner — SSH bootstrap after VPS is ready."""
import asyncio
import logging

logger = logging.getLogger("mms.provisioner")


async def wait_for_ssh(ip: str, port: int = 22, timeout: int = 300) -> bool:
    """Wait until SSH is reachable on the instance."""
    elapsed = 0
    interval = 5
    while elapsed < timeout:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=5,
            )
            writer.close()
            await writer.wait_closed()
            logger.info("SSH reachable at %s:%d after %ds", ip, port, elapsed)
            return True
        except (OSError, asyncio.TimeoutError):
            await asyncio.sleep(interval)
            elapsed += interval
    logger.error("SSH not reachable at %s:%d after %ds", ip, port, timeout)
    return False


async def run_ssh_command(ip: str, command: str, key_path: str, user: str = "root", timeout: int = 120) -> tuple[str, int]:
    """Run a command on the instance via SSH."""
    ssh_opts = (
        f"-i {key_path} "
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o ConnectTimeout=10 "
        "-o LogLevel=ERROR"
    )
    full_cmd = f"ssh {ssh_opts} {user}@{ip} {command!r}"
    try:
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace")
        logger.info("SSH %s@%s [%d]: %s", user, ip, proc.returncode, command)
        return output, proc.returncode
    except asyncio.TimeoutError:
        logger.error("SSH command timed out: %s", command)
        return "Command timed out", -1
    except Exception as e:
        logger.error("SSH error: %s", e)
        return str(e), -1


async def scp_upload(ip: str, local_path: str, remote_path: str, key_path: str, user: str = "root") -> bool:
    """Upload a file or directory to the instance via SCP."""
    ssh_opts = (
        f"-i {key_path} "
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o LogLevel=ERROR"
    )
    cmd = f"scp {ssh_opts} -r {local_path} {user}@{ip}:{remote_path}"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0:
            logger.info("SCP upload to %s:%s successful", ip, remote_path)
            return True
        else:
            logger.error("SCP failed: %s", stdout.decode(errors="replace"))
            return False
    except Exception as e:
        logger.error("SCP error: %s", e)
        return False


async def setup_ssl(ip: str, domain: str, key_path: str) -> tuple[str, int]:
    """Run certbot for SSL on the instance."""
    cmd = f"certbot --nginx -d {domain} --non-interactive --agree-tos --email admin@{domain} --redirect"
    return await run_ssh_command(ip, cmd, key_path)
