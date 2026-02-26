"""Instance type definitions — what each type provisions."""
import base64
from pathlib import Path

from server.config import settings

CLOUD_INIT_DIR = Path(__file__).parent.parent.parent / "base"


# Default cloud-init scripts per instance type
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
        "cloud_init": None,  # Runpod handles this
        "features": ["cuda", "python", "pytorch", "jupyter"],
    },
    "custom": {
        "description": "User-defined specifications",
        "default_plan": "vc2-1c-1gb",
        "cloud_init": "cloud-init.yaml",
        "features": [],
    },
}


def get_cloud_init(instance_type: str, domain: str | None = None) -> str:
    """Load and customize cloud-init for an instance type."""
    config = INSTANCE_CONFIGS.get(instance_type, INSTANCE_CONFIGS["custom"])
    template_name = config.get("cloud_init")

    if not template_name:
        return ""

    template_path = CLOUD_INIT_DIR / template_name
    if not template_path.exists():
        return ""

    content = template_path.read_text()

    # Replace placeholders
    content = content.replace("{{DOMAIN}}", domain or "localhost")
    content = content.replace("{{VULTR_API_KEY}}", settings.VULTR_API_KEY)
    content = content.replace("{{CF_API_TOKEN}}", settings.CF_API_TOKEN)
    content = content.replace("{{ADMIN_EMAIL}}", settings.ADMIN_EMAIL)
    content = content.replace("{{GIT_BRANCH}}", "main")
    content = content.replace("{{R2_ENDPOINT}}", settings.R2_ENDPOINT)
    content = content.replace("{{R2_ACCESS_KEY_ID}}", settings.R2_ACCESS_KEY_ID)
    content = content.replace("{{R2_SECRET_ACCESS_KEY}}", settings.R2_SECRET_ACCESS_KEY)
    content = content.replace("{{R2_BUCKET}}", settings.R2_BUCKET)

    return base64.b64encode(content.encode()).decode()


def get_type_info(instance_type: str) -> dict:
    config = INSTANCE_CONFIGS.get(instance_type, INSTANCE_CONFIGS["custom"])
    return {
        "type": instance_type,
        "description": config["description"],
        "default_plan": config["default_plan"],
        "features": config["features"],
    }
