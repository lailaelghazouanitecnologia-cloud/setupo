"""
Validation runners — execute checks by type.

Each runner receives a resolved config dict and returns (status, output, error).
Status is: "pass" | "fail" | "skip" | "error"
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Any

import httpx

logger = logging.getLogger("nso.validator.runners")


# ── Runner registry ──

RUNNER_TYPES: dict[str, Any] = {}


def _register(type_name: str):
    def decorator(func):
        RUNNER_TYPES[type_name] = func
        return func
    return decorator


async def run_check(check_type: str, config: dict) -> tuple[str, str, str]:
    """
    Dispatch to the appropriate runner.

    Returns: (status, output, error)
    """
    runner = RUNNER_TYPES.get(check_type)
    if not runner:
        return "skip", "", f"Unknown check type: {check_type}"
    return await runner(config)


# ── HTTP Runner ──

@_register("http")
async def run_http(config: dict) -> tuple[str, str, str]:
    """
    HTTP check — verify endpoint responds as expected.

    Config:
        url: str               — URL to check (required)
        method: str             — HTTP method (default: GET)
        expect_status: int      — Expected status code (default: 200)
        expect_body_contains: str — String that must appear in body
        expect_body_not_contains: str — String that must NOT appear
        headers: dict           — Custom headers
        body: str               — Request body (for POST/PUT)
        timeout: int            — Timeout in seconds (default: 10)
        follow_redirects: bool  — Follow redirects (default: true)
    """
    url = config.get("url", "")
    if not url:
        return "error", "", "No URL provided"

    method = config.get("method", "GET").upper()
    expect_status = config.get("expect_status", 200)
    expect_body = config.get("expect_body_contains", "")
    expect_not_body = config.get("expect_body_not_contains", "")
    headers = config.get("headers", {})
    body = config.get("body", "")
    timeout = config.get("timeout", 10)
    follow_redirects = config.get("follow_redirects", True)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
        ) as client:
            kwargs: dict[str, Any] = {"headers": headers}
            if body and method in ("POST", "PUT", "PATCH"):
                kwargs["content"] = body

            resp = await client.request(method, url, **kwargs)

        output = f"HTTP {resp.status_code} {resp.reason_phrase}"
        response_text = resp.text[:2000]

        # Status check
        if resp.status_code != expect_status:
            return "fail", output, f"Expected status {expect_status}, got {resp.status_code}"

        # Body contains check
        if expect_body and expect_body not in response_text:
            return "fail", output, f"Response body does not contain: {expect_body[:200]}"

        # Body not contains check
        if expect_not_body and expect_not_body in response_text:
            return "fail", output, f"Response body contains forbidden: {expect_not_body[:200]}"

        return "pass", output, ""

    except httpx.TimeoutException:
        return "fail", "", f"Timeout after {timeout}s"
    except httpx.ConnectError as e:
        return "fail", "", f"Connection failed: {e}"
    except Exception as e:
        return "error", "", str(e)


# ── Command Runner ──

@_register("command")
async def run_command(config: dict) -> tuple[str, str, str]:
    """
    Command check — execute a shell command on the server or via agent.

    Config:
        command: str            — Command to execute (required)
        expect_exit: int        — Expected exit code (default: 0)
        expect_output_contains: str — String that must appear in stdout
        timeout: int            — Timeout in seconds (default: 60)
        cwd: str                — Working directory
        env: dict               — Extra environment variables

    For remote execution (on VPS), the routes layer handles dispatching
    via the agent HTTP API. This runner executes locally.
    """
    command = config.get("command", "")
    if not command:
        return "error", "", "No command provided"

    expect_exit = config.get("expect_exit", 0)
    expect_output = config.get("expect_output_contains", "")
    timeout = config.get("timeout", 60)
    cwd = config.get("cwd", None)
    env_extra = config.get("env", {})

    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )

        stdout_str = stdout.decode(errors="replace")[:4000]
        stderr_str = stderr.decode(errors="replace")[:2000]
        exit_code = proc.returncode or 0

        output = stdout_str
        if stderr_str:
            output += f"\n--- stderr ---\n{stderr_str}"

        if exit_code != expect_exit:
            return "fail", output, f"Exit code {exit_code}, expected {expect_exit}"

        if expect_output and expect_output not in stdout_str:
            return "fail", output, f"Output does not contain: {expect_output[:200]}"

        return "pass", output, ""

    except asyncio.TimeoutError:
        return "fail", "", f"Command timed out after {timeout}s"
    except Exception as e:
        return "error", "", str(e)


# ── TCP Runner ──

@_register("tcp")
async def run_tcp(config: dict) -> tuple[str, str, str]:
    """
    TCP check — verify a port is open and accepting connections.

    Config:
        host: str               — Hostname/IP (default: localhost)
        port: int               — Port number (required)
        timeout: int            — Timeout in seconds (default: 5)
    """
    host = config.get("host", "localhost")
    port = config.get("port")
    timeout = config.get("timeout", 5)

    if not port:
        return "error", "", "No port provided"

    try:
        port = int(port)
    except (ValueError, TypeError):
        return "error", "", f"Invalid port: {port}"

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return "pass", f"TCP {host}:{port} open", ""

    except asyncio.TimeoutError:
        return "fail", "", f"Connection to {host}:{port} timed out after {timeout}s"
    except ConnectionRefusedError:
        return "fail", "", f"Connection to {host}:{port} refused"
    except OSError as e:
        return "fail", "", f"Cannot connect to {host}:{port}: {e}"


# ── Environment Variable Runner ──

@_register("env")
async def run_env(config: dict) -> tuple[str, str, str]:
    """
    Env check — verify environment variables are set.

    Config:
        required: list[str]     — Env vars that must exist and be non-empty
        optional: list[str]     — Env vars to check (warn if missing, don't fail)
        secrets: dict           — Project secrets to check against (injected by routes)
    """
    required = config.get("required", [])
    secrets = config.get("secrets", {})

    if not required:
        return "skip", "", "No required env vars specified"

    missing = []
    found = []

    for var in required:
        # Check both OS env and project secrets
        val = os.environ.get(var, "") or secrets.get(var, "")
        if val:
            found.append(var)
        else:
            missing.append(var)

    if missing:
        return "fail", f"Found: {', '.join(found)}", f"Missing: {', '.join(missing)}"

    return "pass", f"All {len(found)} env vars present", ""


# ── Metric Runner ──

@_register("metric")
async def run_metric(config: dict) -> tuple[str, str, str]:
    """
    Metric check — verify system metrics are within bounds.

    Config:
        metric: str             — Metric name (disk_usage_percent, memory_usage_percent, cpu_load)
        min: float              — Minimum acceptable value (optional)
        max: float              — Maximum acceptable value (optional)
    """
    metric_name = config.get("metric", "")
    min_val = config.get("min")
    max_val = config.get("max")

    if not metric_name:
        return "skip", "", "No metric specified"

    value = await _read_metric(metric_name)
    if value is None:
        return "skip", "", f"Metric '{metric_name}' not available"

    output = f"{metric_name} = {value}"

    if min_val is not None and value < float(min_val):
        return "fail", output, f"{metric_name} ({value}) below minimum ({min_val})"

    if max_val is not None and value > float(max_val):
        return "fail", output, f"{metric_name} ({value}) above maximum ({max_val})"

    return "pass", output, ""


async def _read_metric(name: str) -> float | None:
    """Read a system metric. Returns None if unavailable."""
    try:
        if name == "disk_usage_percent":
            stat = os.statvfs("/")
            used = (stat.f_blocks - stat.f_bfree) / stat.f_blocks * 100
            return round(used, 1)

        elif name == "memory_usage_percent":
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem = {}
            for line in lines[:5]:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
            total = mem.get("MemTotal", 0)
            available = mem.get("MemAvailable", 0)
            if total > 0:
                return round((total - available) / total * 100, 1)

        elif name == "cpu_load":
            with open("/proc/loadavg") as f:
                load_1m = float(f.read().split()[0])
            return load_1m

    except Exception:
        pass

    return None


# ── Remote Command Runner (via agent HTTP) ──

@_register("remote_command")
async def run_remote_command(config: dict) -> tuple[str, str, str]:
    """
    Remote command check — execute command on VPS via agent API.

    Config:
        command: str            — Command to execute
        agent_url: str          — Agent base URL (e.g. http://1.2.3.4:8081)
        agent_token: str        — Agent JWT token
        expect_exit: int        — Expected exit code (default: 0)
        timeout: int            — Timeout in seconds (default: 60)
    """
    command = config.get("command", "")
    agent_url = config.get("agent_url", "")
    agent_token = config.get("agent_token", "")
    expect_exit = config.get("expect_exit", 0)
    timeout = config.get("timeout", 60)

    if not command or not agent_url:
        return "error", "", "Missing command or agent_url"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{agent_url}/exec/",
                headers={"Authorization": f"Bearer {agent_token}"} if agent_token else {},
                json={"command": command},
            )

        if resp.status_code != 200:
            return "error", "", f"Agent returned HTTP {resp.status_code}"

        data = resp.json()
        exit_code = data.get("exit_code", -1)
        stdout = data.get("stdout", "")[:4000]
        stderr = data.get("stderr", "")[:2000]

        output = stdout
        if stderr:
            output += f"\n--- stderr ---\n{stderr}"

        if exit_code != expect_exit:
            return "fail", output, f"Exit code {exit_code}, expected {expect_exit}"

        return "pass", output, ""

    except Exception as e:
        return "error", "", str(e)
