"""
Generators for systemd units, nginx configs, and .env files.

Used by the deploy pipeline to create service infrastructure on the VPS.
"""

from __future__ import annotations

SERVICE_PREFIX = "nso-app"


def generate_systemd_unit(
    svc_name: str,
    svc_config: dict,
    env: dict[str, str],
    working_dir: str,
) -> str:
    """Generate a systemd service unit file.

    svc_config keys:
      command: str           — the command to run
      user: str              — run as user (default: root)
      restart: str           — restart policy (default: always)
      env: dict              — extra env vars for this service
      depends_on: list[str]  — other services this depends on
    """
    command = svc_config.get("command", "")
    user = svc_config.get("user", "root")
    restart = svc_config.get("restart", "always")
    description = svc_config.get("description", f"NSO App - {svc_name}")

    # Merge global env + service-specific env
    merged_env = dict(env)
    svc_env = svc_config.get("env", {})
    if isinstance(svc_env, dict):
        for k, v in svc_env.items():
            merged_env[str(k)] = str(v)

    # Build Environment lines
    env_lines = ""
    for k, v in merged_env.items():
        env_lines += f"Environment={k}={v}\n"

    # systemd dependencies
    after = "network.target"
    wants = ""
    deps = svc_config.get("depends_on", [])
    if isinstance(deps, list):
        for dep in deps:
            unit = f"{SERVICE_PREFIX}-{dep}.service"
            after += f" {unit}"
            wants += f" {unit}"

    unit = f"""[Unit]
Description={description}
After={after}
{f'Wants={wants.strip()}' if wants.strip() else ''}

[Service]
Type=simple
User={user}
WorkingDirectory={working_dir}
ExecStart={command}
Restart={restart}
RestartSec=5
{env_lines}
[Install]
WantedBy=multi-user.target
"""
    # Clean up empty lines from optional fields
    lines = [line for line in unit.splitlines() if line.strip() or line == ""]
    return "\n".join(lines) + "\n"


def generate_nginx_config(config: dict, domains: list[str]) -> str:
    """Generate an nginx server block.

    config keys used:
      nginx.port: int             — upstream app port (default: 3000)
      nginx.static_dir: str       — serve static files from this dir
      nginx.client_max_body: str  — max body size (default: 10m)
      nginx.extra_locations: list — additional location blocks
    """
    nginx = config.get("nginx", {})
    port = nginx.get("port", 3000)
    static_dir = nginx.get("static_dir", "")
    max_body = nginx.get("client_max_body", "10m")
    extra_locations = nginx.get("extra_locations", [])

    server_name = " ".join(domains) if domains else "_"

    locations = ""
    if static_dir:
        locations += f"""
    location / {{
        root {static_dir};
        try_files $uri $uri/ /index.html;
    }}
"""
    else:
        locations += f"""
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
"""

    if isinstance(extra_locations, list):
        for loc in extra_locations:
            if isinstance(loc, dict):
                path = loc.get("path", "/extra")
                content = loc.get("content", "")
                locations += f"\n    location {path} {{\n        {content}\n    }}\n"

    return f"""server {{
    listen 80;
    server_name {server_name};
    client_max_body_size {max_body};
{locations}
}}
"""


def generate_env_file(env: dict[str, str]) -> str:
    """Generate .env file content from a dict of env vars."""
    lines = []
    for k, v in sorted(env.items()):
        # Quote values containing spaces or special chars
        if " " in v or "'" in v or '"' in v or "=" in v or "\n" in v:
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k}="{escaped}"')
        else:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n" if lines else ""
