"""
Generators for systemd unit files and nginx server blocks from deploy.toml config.
"""

import logging
from typing import Any

logger = logging.getLogger("nso-agent.generators")

SERVICE_PREFIX = "nso-app"


def generate_systemd_unit(
    service_name: str,
    config: dict[str, Any],
    env: dict[str, str] | None = None,
    working_dir: str = "/opt/app",
) -> str:
    """Generate a systemd unit file for a service definition.

    Args:
        service_name: Short name (e.g. "web", "worker")
        config: Service config from deploy.toml [services.<name>]
        env: Resolved environment variables
        working_dir: Working directory for the service
    """
    unit_name = f"{SERVICE_PREFIX}-{service_name}"
    command = config.get("command", "")
    user = config.get("user", "root")
    restart = config.get("restart", "on-failure")
    svc_working_dir = config.get("working_dir", working_dir)
    depends = config.get("depends_on", [])

    # Build After/Requires from depends_on
    after_units = ["network.target"]
    requires_units = []
    if isinstance(depends, list):
        for dep in depends:
            dep_unit = f"{SERVICE_PREFIX}-{dep}.service"
            after_units.append(dep_unit)
            requires_units.append(dep_unit)

    # Build Environment lines for service-level env
    svc_env = config.get("env", {})
    env_lines = []
    if isinstance(svc_env, dict):
        for k, v in svc_env.items():
            env_lines.append(f"Environment={k}={v}")

    # Port as env var
    port = config.get("port")
    if port:
        env_lines.append(f"Environment=PORT={port}")

    after_str = " ".join(after_units)
    lines = [
        "[Unit]",
        f"Description=NSO App - {service_name}",
        f"After={after_str}",
    ]
    if requires_units:
        lines.append(f"Requires={' '.join(requires_units)}")

    lines.extend([
        "",
        "[Service]",
        "Type=simple",
        f"User={user}",
        f"WorkingDirectory={svc_working_dir}",
        f"EnvironmentFile=-{svc_working_dir}/.env",
        f"ExecStart=/bin/bash -c '{command}'",
        f"Restart={restart}",
        "RestartSec=5",
        "StandardOutput=journal",
        "StandardError=journal",
    ])
    lines.extend(env_lines)
    lines.extend([
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ])

    return "\n".join(lines) + "\n"


def generate_nginx_config(
    deploy_config: dict[str, Any],
    domains: list[str] | None = None,
) -> str:
    """Generate nginx server block from deploy.toml [nginx] config.

    Args:
        deploy_config: Full deploy.toml parsed dict
        domains: List of domain names for server_name directive
    """
    nginx = deploy_config.get("nginx", {})
    nginx_type = nginx.get("type", "proxy")

    # Collect domain names
    domain_list = list(domains or [])
    config_domains = deploy_config.get("domains", [])
    if isinstance(config_domains, list):
        for d in config_domains:
            if isinstance(d, dict) and d.get("name"):
                name = d["name"]
                if name not in domain_list:
                    domain_list.append(name)
    if not domain_list:
        domain_list = ["_"]

    server_name = " ".join(domain_list)

    # Global headers
    headers = nginx.get("headers", {})
    header_lines = []
    if isinstance(headers, dict):
        for k, v in headers.items():
            header_lines.append(f'    add_header {k} "{v}";')

    # Extra locations
    locations = nginx.get("locations", [])
    location_blocks = []
    if isinstance(locations, list):
        for loc in locations:
            if not isinstance(loc, dict):
                continue
            path = loc.get("path", "")
            alias = loc.get("alias", "")
            loc_headers = loc.get("headers", {})
            block = [f"    location {path} {{"]
            if alias:
                block.append(f"        alias {alias};")
            if isinstance(loc_headers, dict):
                for k, v in loc_headers.items():
                    block.append(f'        add_header {k} "{v}";')
            block.append("    }")
            location_blocks.append("\n".join(block))

    # Main location block
    if nginx_type == "proxy":
        proxy = nginx.get("proxy", {})
        target = proxy.get("target", "http://127.0.0.1:3000")
        websocket = proxy.get("websocket", False)
        read_timeout = proxy.get("read_timeout", "60s")
        body_max_size = proxy.get("body_max_size", "10m")

        main_location = [
            "    location / {",
            f"        proxy_pass {target};",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            f"        proxy_read_timeout {read_timeout};",
            f"        client_max_body_size {body_max_size};",
        ]
        if websocket:
            main_location.extend([
                "        proxy_http_version 1.1;",
                "        proxy_set_header Upgrade $http_upgrade;",
                '        proxy_set_header Connection "upgrade";',
            ])
        main_location.append("    }")
        main_location_str = "\n".join(main_location)

    elif nginx_type == "static":
        static = nginx.get("static", {})
        root = static.get("root", "/opt/app/dist")
        index = static.get("index", "index.html")
        spa = static.get("spa", False)
        cache = static.get("cache", "")

        main_location = [
            "    location / {",
            f"        root {root};",
            f"        index {index};",
        ]
        if spa:
            main_location.append(f"        try_files $uri $uri/ /{index};")
        if cache:
            main_location.append(f'        add_header Cache-Control "public, max-age={_cache_seconds(cache)}";')
        main_location.append("    }")
        main_location_str = "\n".join(main_location)

    elif nginx_type == "custom":
        # User provides their own config; we just return a placeholder
        custom_path = nginx.get("custom", {}).get("config_path", "")
        return f"# Custom nginx config — include {custom_path}\ninclude {custom_path};\n"

    else:
        main_location_str = "    location / {\n        return 502;\n    }"

    # SSL config (placeholder paths — certbot will populate)
    ssl_lines = [
        f"    ssl_certificate /etc/letsencrypt/live/{domain_list[0]}/fullchain.pem;",
        f"    ssl_certificate_key /etc/letsencrypt/live/{domain_list[0]}/privkey.pem;",
    ]

    # Build the full config
    config_lines = [
        f"# Auto-generated by NSO deploy pipeline",
        f"server {{",
        f"    listen 443 ssl;",
        f"    server_name {server_name};",
        "",
    ]
    config_lines.extend(ssl_lines)
    config_lines.append("")

    if header_lines:
        config_lines.extend(header_lines)
        config_lines.append("")

    config_lines.append(main_location_str)
    config_lines.append("")

    for loc_block in location_blocks:
        config_lines.append(loc_block)
        config_lines.append("")

    config_lines.append("}")
    config_lines.append("")

    # HTTP → HTTPS redirect
    config_lines.extend([
        "server {",
        "    listen 80;",
        f"    server_name {server_name};",
        "    return 301 https://$host$request_uri;",
        "}",
    ])

    return "\n".join(config_lines) + "\n"


def generate_env_file(env: dict[str, str]) -> str:
    """Generate a .env file from resolved env vars."""
    lines = []
    for k, v in sorted(env.items()):
        # Escape quotes in values
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{k}="{escaped}"')
    return "\n".join(lines) + "\n"


def _cache_seconds(val: str) -> int:
    """Convert cache duration string like '7d', '1h' to seconds."""
    val = val.strip().lower()
    if val.endswith("d"):
        return int(val[:-1]) * 86400
    if val.endswith("h"):
        return int(val[:-1]) * 3600
    if val.endswith("m"):
        return int(val[:-1]) * 60
    try:
        return int(val)
    except ValueError:
        return 86400
