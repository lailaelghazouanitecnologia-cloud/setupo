import asyncio
import logging
import re
import shlex

logger = logging.getLogger("nso.provisioner")

SSH_CONNECT_TIMEOUT = 5
SSH_POLL_INTERVAL = 5
SSH_CMD_TIMEOUT = 120
SCP_TIMEOUT = 300

# Validate SSH parameters to prevent injection
_SAFE_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_SAFE_IP_RE = re.compile(r"^[0-9a-fA-F.:]+$")  # IPv4 or IPv6
_SAFE_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,253}[a-zA-Z0-9])?$")


def _validate_ssh_user(user: str) -> str:
    if not _SAFE_USER_RE.match(user):
        raise ValueError(f"Invalid SSH user: {user!r}")
    return user


def _validate_ip(ip: str) -> str:
    if not _SAFE_IP_RE.match(ip):
        raise ValueError(f"Invalid IP address: {ip!r}")
    return ip


def _validate_domain(domain: str) -> str:
    if not _SAFE_DOMAIN_RE.match(domain) or len(domain) > 255:
        raise ValueError(f"Invalid domain: {domain!r}")
    if ".." in domain:
        raise ValueError(f"Invalid domain (double dot): {domain!r}")
    return domain


def _validate_path(path: str) -> str:
    """Validate a filesystem path has no injection characters."""
    if any(c in path for c in (";", "|", "&", "`", "$", "(", ")", "\n", "\r")):
        raise ValueError(f"Invalid characters in path: {path!r}")
    return path


async def wait_for_ssh(ip: str, port: int = 22, timeout: int = 300) -> bool:
    _validate_ip(ip)
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
    """Execute a command on a remote host via SSH using subprocess_exec (no shell)."""
    _validate_ip(ip)
    _validate_ssh_user(user)
    _validate_path(key_path)

    # Build SSH command as argv list — no shell interpretation
    argv = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "LogLevel=ERROR",
        f"{user}@{ip}",
        command,  # SSH passes this as a single argument to remote shell
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace")
        logger.info("SSH %s@%s [%d]: %s", user, ip, proc.returncode, command[:200])
        return output, proc.returncode
    except asyncio.TimeoutError:
        logger.error("SSH command timed out: %s", command[:200])
        try:
            proc.kill()
        except Exception:
            pass
        return "Command timed out", -1
    except Exception as e:
        logger.error("SSH error: %s", e)
        return str(e), -1


async def scp_upload(ip: str, local_path: str, remote_path: str, key_path: str, user: str = "root") -> bool:
    """Upload a file via SCP using subprocess_exec (no shell)."""
    _validate_ip(ip)
    _validate_ssh_user(user)
    _validate_path(key_path)
    _validate_path(local_path)
    _validate_path(remote_path)

    # Build SCP command as argv list — no shell interpretation
    argv = [
        "scp",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        "-o", "LogLevel=ERROR",
        "-r",
        local_path,
        f"{user}@{ip}:{remote_path}",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
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
    """Set up SSL via certbot on a remote host."""
    _validate_domain(domain)
    cmd = f"certbot --nginx -d {shlex.quote(domain)} --non-interactive --agree-tos --email admin@{shlex.quote(domain)} --redirect"
    return await run_ssh_command(ip, cmd, key_path)
