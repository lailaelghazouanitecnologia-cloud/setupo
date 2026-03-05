import base64
import secrets
from pathlib import Path

from nso.config import settings

CLOUD_INIT_DIR = Path(__file__).parent.parent.parent / "base"

INSTANCE_CONFIGS = {
    "setup": {
        "description": "Basic server with nginx, SSL-ready, optimized for quick deploy",
        "default_plan": "vc2-1c-1gb",
        "cloud_init": "cloud-init.yaml",
        "features": ["nginx", "certbot", "node", "python", "git", "ufw"],
    },
    "dev": {
        "description": "Full development environment with tooling",
        "default_plan": "vc2-1c-2gb",
        "cloud_init": "cloud-init.yaml",
        "features": ["nginx", "node", "python", "git", "ufw"],
    },
    "gpu": {
        "description": "GPU-powered instance for ML/AI workloads (Runpod)",
        "default_plan": "gpu-a40",
        "cloud_init": None,
        "features": ["cuda", "python", "pytorch", "jupyter"],
    },
    "pool_host": {
        "description": "Pool host for running isolated user VMs/containers",
        "default_plan": "vhp-4c-8gb-intel",
        "cloud_init": "cloud-init-pool-host.yaml",
        "features": ["docker", "cgroups", "iptables", "apparmor", "fail2ban"],
    },
    "custom": {
        "description": "User-defined specifications",
        "default_plan": "vc2-1c-1gb",
        "cloud_init": "cloud-init.yaml",
        "features": [],
    },
}


def get_cloud_init(
    instance_type: str,
    domain: str | None = None,
    git_url: str | None = None,
    git_branch: str = "main",
    app_ready_key: str = "",
    pool_agent_token: str = "",
    central_server_ip: str = "",
) -> str:
    config = INSTANCE_CONFIGS.get(instance_type, INSTANCE_CONFIGS["custom"])
    template_name = config.get("cloud_init")

    if not template_name:
        return ""

    template_path = CLOUD_INIT_DIR / template_name
    if not template_path.exists():
        return ""

    content = template_path.read_text()

    # Common replacements
    replacements = {
        "{{DOMAIN}}": domain or "localhost",
        "{{ADMIN_EMAIL}}": settings.ADMIN_EMAIL,
        "{{ADMIN_PASSWORD}}": settings.ADMIN_PASSWORD or settings.AGENT_ADMIN_PASSWORD,
        "{{JWT_SECRET}}": secrets.token_hex(32),
    }

    if instance_type == "pool_host":
        # Pool hosts only get what they need — no user-facing secrets
        replacements.update({
            "{{POOL_AGENT_TOKEN}}": pool_agent_token,
            "{{CENTRAL_SERVER_IP}}": central_server_ip or getattr(settings, "NSO_HOST", "0.0.0.0"),
        })
    else:
        # User instances get deploy-related config
        replacements.update({
            "{{VULTR_API_KEY}}": settings.VULTR_API_KEY,
            "{{CF_API_TOKEN}}": settings.CF_API_TOKEN,
            "{{GIT_BRANCH}}": git_branch or "master",
            "{{CF_NSO_ZONE_ID}}": getattr(settings, "CF_NSO_ZONE_ID", ""),
            "{{R2_ENDPOINT}}": settings.R2_ENDPOINT,
            "{{R2_ACCESS_KEY_ID}}": settings.R2_ACCESS_KEY_ID,
            "{{R2_SECRET_ACCESS_KEY}}": settings.R2_SECRET_ACCESS_KEY,
            "{{R2_BUCKET}}": settings.R2_BUCKET,
            "{{R2_READY_BUCKET}}": settings.R2_READY_BUCKET,
            "{{APP_GIT_URL}}": git_url or "",
            "{{APP_GIT_BRANCH}}": git_branch or "main",
            "{{APP_READY_KEY}}": app_ready_key or "",
        })

    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    return base64.b64encode(content.encode()).decode()


def get_type_info(instance_type: str) -> dict:
    config = INSTANCE_CONFIGS.get(instance_type, INSTANCE_CONFIGS["custom"])
    return {
        "type": instance_type,
        "description": config["description"],
        "default_plan": config["default_plan"],
        "features": config["features"],
    }
