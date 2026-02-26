"""Workspace config.toml manager — read/write workspace configuration files.

Uses tomli for reading (stdlib tomllib in 3.11+) and manual TOML generation
for writing to avoid extra dependencies.
"""
import os
import logging
from pathlib import Path
from typing import Optional

from core.models import (
    WorkspaceConfig,
    WorkspaceGitConfig,
    WorkspaceDeployConfig,
    WorkspaceServiceConfig,
    PackageConfig,
    ZarDependency,
    R2Config,
)

logger = logging.getLogger("setupo.workspace_config")

CONFIG_FILENAME = "config.toml"


def _parse_toml(text: str) -> dict:
    """Minimal TOML parser for our config.toml format.

    Handles: [sections], [section.subsections], key = "string", key = number,
    key = true/false. Enough for our workspace configs.
    """
    result = {}
    current_section = result
    current_path: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            parts = section_name.split(".")
            current_section = result
            current_path = parts
            for part in parts:
                if part not in current_section:
                    current_section[part] = {}
                current_section = current_section[part]
            continue

        # Key = value
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Parse value
            if value.startswith('"') and value.endswith('"'):
                parsed = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                parsed = value[1:-1]
            elif value.lower() == "true":
                parsed = True
            elif value.lower() == "false":
                parsed = False
            elif value.isdigit():
                parsed = int(value)
            else:
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = value

            current_section[key] = parsed

    return result


def _to_toml(data: dict, prefix: str = "") -> str:
    """Convert a dict to TOML string."""
    lines = []
    simple_keys = {}
    nested_keys = {}

    for key, value in data.items():
        if isinstance(value, dict):
            nested_keys[key] = value
        else:
            simple_keys[key] = value

    # Write simple keys first
    for key, value in simple_keys.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        elif isinstance(value, float):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f'{key} = "{value}"')

    # Write nested sections
    for key, value in nested_keys.items():
        section = f"{prefix}.{key}" if prefix else key
        lines.append("")
        lines.append(f"[{section}]")
        for k, v in value.items():
            if isinstance(v, dict):
                sub_section = f"{section}.{k}"
                lines.append("")
                lines.append(f"[{sub_section}]")
                for sk, sv in v.items():
                    if isinstance(sv, bool):
                        lines.append(f"{sk} = {str(sv).lower()}")
                    elif isinstance(sv, (int, float)):
                        lines.append(f"{sk} = {sv}")
                    else:
                        lines.append(f'{sk} = "{sv}"')
            elif isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            else:
                lines.append(f'{k} = "{v}"')

    return "\n".join(lines) + "\n"


def generate_config_toml(config: WorkspaceConfig) -> str:
    """Generate a config.toml string from a WorkspaceConfig model."""
    lines = [
        "[workspace]",
        f'name = "{config.name}"',
        f'type = "{config.type}"',
        f'description = "{config.description}"',
    ]

    # Git section
    if config.git.url:
        lines.extend([
            "",
            "[workspace.git]",
            f'url = "{config.git.url}"',
            f'branch = "{config.git.branch}"',
            f"auto_pull = {str(config.git.auto_pull).lower()}",
        ])

    # Deploy section
    lines.extend([
        "",
        "[deploy]",
    ])
    if config.deploy.instance_id:
        lines.append(f'instance_id = "{config.deploy.instance_id}"')
    if config.deploy.command:
        lines.append(f'command = "{config.deploy.command}"')
    lines.append(f"port = {config.deploy.port}")

    # Deploy env vars
    if config.deploy.env:
        lines.extend([
            "",
            "[deploy.env]",
        ])
        for k, v in config.deploy.env.items():
            lines.append(f'{k} = "{v}"')

    # Services
    for svc_name, svc_config in config.services.items():
        lines.extend([
            "",
            f"[services.{svc_name}]",
            f"enabled = {str(svc_config.enabled).lower()}",
        ])
        if svc_config.domain:
            lines.append(f'domain = "{svc_config.domain}"')
        lines.append(f"ssl = {str(svc_config.ssl).lower()}")

    return "\n".join(lines) + "\n"


def read_config(workspace_path: str) -> Optional[WorkspaceConfig]:
    """Read config.toml from a workspace directory. Returns None if not found."""
    config_path = os.path.join(workspace_path, CONFIG_FILENAME)
    if not os.path.isfile(config_path):
        return None

    try:
        with open(config_path, "r") as f:
            raw = _parse_toml(f.read())

        ws_data = raw.get("workspace", {})
        git_data = ws_data.pop("git", {})
        deploy_data = raw.get("deploy", {})
        env_data = deploy_data.pop("env", {})
        services_raw = raw.get("services", {})

        config = WorkspaceConfig(
            name=ws_data.get("name", ""),
            type=ws_data.get("type", "custom"),
            description=ws_data.get("description", ""),
            git=WorkspaceGitConfig(
                url=git_data.get("url"),
                branch=git_data.get("branch", "main"),
                auto_pull=git_data.get("auto_pull", False),
            ),
            deploy=WorkspaceDeployConfig(
                instance_id=deploy_data.get("instance_id"),
                command=deploy_data.get("command"),
                port=deploy_data.get("port", 3000),
                env=env_data,
            ),
            services={
                name: WorkspaceServiceConfig(
                    enabled=svc.get("enabled", True),
                    domain=svc.get("domain"),
                    ssl=svc.get("ssl", True),
                )
                for name, svc in services_raw.items()
                if isinstance(svc, dict)
            },
        )
        return config
    except Exception as e:
        logger.warning("Failed to read config.toml at %s: %s", config_path, e)
        return None


def read_package_config(workspace_path: str) -> PackageConfig | None:
    """Read [package] section from config.toml. Returns None if not found."""
    config_path = os.path.join(workspace_path, CONFIG_FILENAME)
    if not os.path.isfile(config_path):
        return None

    try:
        with open(config_path, "r") as f:
            raw = _parse_toml(f.read())

        pkg_data = raw.get("package", {})
        if not pkg_data:
            return None

        deps_raw = pkg_data.get("dependencies", {})
        deps = {}
        for name, cfg in deps_raw.items():
            if isinstance(cfg, dict):
                deps[name] = ZarDependency(
                    name=name,
                    branch=cfg.get("branch", "main"),
                    version=cfg.get("version", ""),
                    path=cfg.get("path", f"deps/{name}"),
                )
            elif isinstance(cfg, str):
                deps[name] = ZarDependency(name=name, branch=cfg)

        return PackageConfig(
            version=str(pkg_data.get("version", "0.1.0")),
            branch=pkg_data.get("branch", "main"),
            dependencies=deps,
        )
    except Exception as e:
        logger.warning("Failed to read [package] from %s: %s", config_path, e)
        return None


def read_r2_config(workspace_path: str) -> R2Config | None:
    """Read [package.r2] section from config.toml."""
    config_path = os.path.join(workspace_path, CONFIG_FILENAME)
    if not os.path.isfile(config_path):
        return None

    try:
        with open(config_path, "r") as f:
            raw = _parse_toml(f.read())

        pkg = raw.get("package", {})
        r2_data = pkg.get("r2", {})
        if not r2_data:
            return None

        return R2Config(
            bucket=r2_data.get("bucket", "nso"),
            endpoint=r2_data.get("endpoint", ""),
            access_key_id=r2_data.get("access_key_id", ""),
            secret_access_key=r2_data.get("secret_access_key", ""),
            public_url=r2_data.get("public_url", ""),
        )
    except Exception as e:
        logger.warning("Failed to read [package.r2] from %s: %s", config_path, e)
        return None


def write_config(workspace_path: str, config: WorkspaceConfig) -> str:
    """Write config.toml to a workspace directory. Returns the file path."""
    os.makedirs(workspace_path, exist_ok=True)
    config_path = os.path.join(workspace_path, CONFIG_FILENAME)
    content = generate_config_toml(config)
    with open(config_path, "w") as f:
        f.write(content)
    logger.info("Wrote config.toml to %s", config_path)
    return config_path
