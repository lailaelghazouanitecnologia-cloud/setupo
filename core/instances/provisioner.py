import asyncio
import logging

logger = logging.getLogger("nso.provisioner")

SSH_CONNECT_TIMEOUT = 5
SSH_POLL_INTERVAL = 5
SSH_CMD_TIMEOUT = 120
SCP_TIMEOUT = 300

SSH_OPTS_TEMPLATE = (
    "-i {key_path} "
    "-o StrictHostKeyChecking=no "
    "-o UserKnownHostsFile=/dev/null "
    "-o ConnectTimeout=10 "
    "-o LogLevel=ERROR"
)


async def wait_for_ssh(ip: str, port: int = 22, timeout: int = 300) -> bool:
    elapsed = 0
    while elapsed < timeout:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=SSH_CONNECT_TIMEOUT,
            )
            writer.close()
            await writer.wait_closed()
            logger.info("SSH reachable at %s:%d after %ds", ip, port, elapsed)
            return True
        except (OSError, asyncio.TimeoutError):
            await asyncio.sleep(SSH_POLL_INTERVAL)
            elapsed += SSH_POLL_INTERVAL
    logger.error("SSH not reachable at %s:%d after %ds", ip, port, timeout)
    return False


async def run_ssh_command(ip: str, command: str, key_path: str, user: str = "root", timeout: int = SSH_CMD_TIMEOUT) -> tuple[str, int]:
    ssh_opts = SSH_OPTS_TEMPLATE.format(key_path=key_path)
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
    ssh_opts = SSH_OPTS_TEMPLATE.format(key_path=key_path)
    cmd = f"scp {ssh_opts} -r {local_path} {user}@{ip}:{remote_path}"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=SCP_TIMEOUT)
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
    cmd = f"certbot --nginx -d {domain} --non-interactive --agree-tos --email admin@{domain} --redirect"
    return await run_ssh_command(ip, cmd, key_path)
