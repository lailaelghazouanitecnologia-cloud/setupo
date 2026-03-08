"""
Health check runner for deploy pipeline.

Supports strategies:
  - http: Check HTTP endpoint returns expected status
  - tcp: Check TCP port is open
  - command: Run a shell command and check exit code
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger("nso-agent.healthcheck")

DEFAULT_RETRIES = 3
DEFAULT_INTERVAL = 5
DEFAULT_TIMEOUT = 10


async def run_health_check(health: dict) -> tuple[bool, str]:
    """Run a health check based on config.

    health keys:
      strategy: str        — "http", "tcp", "command", "none"
      url: str             — for http strategy
      port: int            — for tcp strategy
      command: str         — for command strategy
      expected_status: int — expected HTTP status (default: 200)
      retries: int         — number of retries (default: 3)
      interval: int        — seconds between retries (default: 5)
      timeout: int         — per-attempt timeout in seconds (default: 10)
    """
    strategy = health.get("strategy", "http")
    retries = health.get("retries", DEFAULT_RETRIES)
    interval = health.get("interval", DEFAULT_INTERVAL)
    timeout = health.get("timeout", DEFAULT_TIMEOUT)

    if strategy == "none":
        return True, "Health check skipped"

    for attempt in range(1, retries + 1):
        try:
            if strategy == "http":
                ok, msg = await _check_http(health, timeout)
            elif strategy == "tcp":
                ok, msg = await _check_tcp(health, timeout)
            elif strategy == "command":
                ok, msg = await _check_command(health, timeout)
            else:
                return False, f"Unknown health check strategy: {strategy}"

            if ok:
                return True, f"Health check passed (attempt {attempt}): {msg}"

            logger.warning("Health check attempt %d/%d failed: %s", attempt, retries, msg)
        except Exception as exc:
            logger.warning("Health check attempt %d/%d error: %s", attempt, retries, exc)
            msg = str(exc)

        if attempt < retries:
            await asyncio.sleep(interval)

    return False, f"Health check failed after {retries} attempts: {msg}"


async def _check_http(health: dict, timeout: int) -> tuple[bool, str]:
    """Check an HTTP endpoint."""
    url = health.get("url", "http://127.0.0.1:3000/")
    expected = health.get("expected_status", 200)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)

    if resp.status_code == expected:
        return True, f"HTTP {resp.status_code}"
    return False, f"HTTP {resp.status_code} (expected {expected})"


async def _check_tcp(health: dict, timeout: int) -> tuple[bool, str]:
    """Check a TCP port is open."""
    host = health.get("host", "127.0.0.1")
    port = health.get("port", 3000)

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True, f"TCP {host}:{port} open"
    except (ConnectionRefusedError, OSError) as exc:
        return False, f"TCP {host}:{port} refused: {exc}"


async def _check_command(health: dict, timeout: int) -> tuple[bool, str]:
    """Run a command and check exit code."""
    command = health.get("command", "")
    if not command:
        return False, "No command specified"

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return False, f"Command timed out after {timeout}s"

    output = stdout.decode(errors="replace").strip()
    if proc.returncode == 0:
        return True, output[:200]
    return False, f"Exit code {proc.returncode}: {output[:200]}"
