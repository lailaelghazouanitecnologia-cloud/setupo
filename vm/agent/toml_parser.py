"""
TOML parser + secret resolution + env merging for deploy.toml.

Functions:
  - parse_toml: Parse raw TOML text into a dict
  - resolve_secrets: Replace ${SECRET_NAME} placeholders with actual values
  - merge_env: Merge all env vars from config sections into a single dict
"""

from __future__ import annotations

import re
import tomllib


def parse_toml(content: str) -> dict:
    """Parse raw TOML text into a dictionary."""
    return tomllib.loads(content)


def resolve_secrets(config: dict, secrets: dict[str, str]) -> dict:
    """Recursively replace ${SECRET_NAME} placeholders in config values.

    Supports patterns:
      ${SECRET_NAME}         — required, raises if missing
      ${SECRET_NAME:-default} — optional with default value
    """
    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")

    def _resolve_value(value):
        if isinstance(value, str):
            def _replacer(m):
                key = m.group(1)
                default = m.group(2)
                if key in secrets:
                    return secrets[key]
                if default is not None:
                    return default
                return m.group(0)  # leave unresolved
            return pattern.sub(_replacer, value)
        elif isinstance(value, dict):
            return {k: _resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_resolve_value(v) for v in value]
        return value

    return _resolve_value(config)


def merge_env(config: dict) -> dict[str, str]:
    """Merge env vars from all config sections into a single flat dict.

    Sources (in priority order, later overrides earlier):
      1. [env] section (global env vars)
      2. [services.*.env] sections (per-service env vars)
    """
    env: dict[str, str] = {}

    # Global env section
    global_env = config.get("env", {})
    if isinstance(global_env, dict):
        for k, v in global_env.items():
            env[str(k)] = str(v)

    # Per-service env (merged, not overriding global by default)
    services = config.get("services", {})
    if isinstance(services, dict):
        for svc_config in services.values():
            if isinstance(svc_config, dict):
                svc_env = svc_config.get("env", {})
                if isinstance(svc_env, dict):
                    for k, v in svc_env.items():
                        if str(k) not in env:
                            env[str(k)] = str(v)

    return env
