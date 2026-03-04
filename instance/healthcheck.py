"""
Health check strategies for post-deploy verification.

Supports: HTTP, TCP, command-based checks with retries.
"""

import asyncio
import logging
import socket
from typing import Any

import httpx

logger = logging.getLogger("nso-agent.healthcheck")


async def run_health_check(config: dict[str, Any]) -> tuple[bool, str]:
    """Run health check based on deploy.toml [health] config.

    Returns:
        (passed, message)
    """
    strategy = config.get("strategy", "none")

    if strategy == "none":
        return True, "Health check skipped (strategy=none)"

    if strategy == "http":
        return await _check_http(config.get("http", {}))

    if strategy == "tcp":
        return await _check_tcp(config.get("tcp", {}))

    if strategy == "command":
        return await _check_command(config.get("command", {}))

    return True, f"Unknown health strategy '{strategy}', skipping"


async def _check_http(cfg: dict[str, Any]) -> tuple[bool, str]:
    """HTTP health check with retries."""
    url = cfg.get("url", "http://localhost:3000/health")
    method = cfg.get("method", "GET").upper()
    expected_status = cfg.get("status", 200)
    timeout = cfg.get("timeout", 10)
    retries = cfg.get("retries", 5)
    interval = cfg.get("interval", 3)
    body_contains = cfg.get("body_contains", "")

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url)

            if resp.status_code != expected_status:
                last_error = f"HTTP {resp.status_code} (expected {expected_status})"
                logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)
            elif body_contains and body_contains not in resp.text:
                last_error = f"Response body missing '{body_contains}'"
                logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)
            else:
                logger.info("Health check passed on attempt %d/%d", attempt, retries)
                return True, f"HTTP {method} {url} -> {resp.status_code} OK"

        except httpx.ConnectError:
            last_error = f"Connection refused to {url}"
            logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)
        except httpx.TimeoutException:
            last_error = f"Timeout after {timeout}s"
            logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)
        except Exception as exc:
            last_error = str(exc)
            logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)

        if attempt < retries:
            await asyncio.sleep(interval)

    return False, f"Health check failed after {retries} attempts: {last_error}"


async def _check_tcp(cfg: dict[str, Any]) -> tuple[bool, str]:
    """TCP port check with retries."""
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 3000)
    timeout = cfg.get("timeout", 5)
    retries = cfg.get("retries", 10)
    interval = cfg.get("interval", 2)

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            loop = asyncio.get_event_loop()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            await loop.run_in_executor(None, sock.connect, (host, int(port)))
            sock.close()
            logger.info("TCP health check passed on attempt %d/%d", attempt, retries)
            return True, f"TCP {host}:{port} reachable"
        except (socket.timeout, ConnectionRefusedError, OSError) as exc:
            last_error = str(exc)
            logger.info("TCP check attempt %d/%d: %s", attempt, retries, last_error)
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if attempt < retries:
            await asyncio.sleep(interval)

    return False, f"TCP check failed after {retries} attempts: {last_error}"


async def _check_command(cfg: dict[str, Any]) -> tuple[bool, str]:
    """Command-based health check with retries."""
    if isinstance(cfg, str):
        cmd = cfg
        timeout = 10
        retries = 5
        interval = 3
    else:
        cmd = cfg.get("run", "")
        timeout = cfg.get("timeout", 10)
        retries = cfg.get("retries", 5)
        interval = cfg.get("interval", 3)

    if not cmd:
        return True, "No health check command specified"

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace").strip()

            if proc.returncode == 0:
                logger.info("Command health check passed on attempt %d/%d", attempt, retries)
                return True, f"Command exited 0: {output[:200]}"
            else:
                last_error = f"Exit code {proc.returncode}: {output[:200]}"
                logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)

        except asyncio.TimeoutError:
            last_error = f"Command timed out after {timeout}s"
            logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)
        except Exception as exc:
            last_error = str(exc)
            logger.info("Health check attempt %d/%d: %s", attempt, retries, last_error)

        if attempt < retries:
            await asyncio.sleep(interval)

    return False, f"Command health check failed after {retries} attempts: {last_error}"
