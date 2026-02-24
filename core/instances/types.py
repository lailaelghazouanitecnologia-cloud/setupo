"""Instance type definitions — what each type provisions."""
import base64
from pathlib import Path

CLOUD_INIT_DIR = Path(__file__).parent.parent.parent / "base"


# Default cloud-init scripts per instance type
INSTANCE_CONFIGS = {
    "setup": {
        "description": "Basic server with nginx, SSL-ready, optimized for quick deploy",
        "default_plan": "vc2-1c-1gb",
        "cloud_init": "cloud-init-setup.yaml",
        "features": ["nginx", "certbot", "node", "python", "git", "ufw"],
    },
    "dev": {
        "description": "Full development environment with tooling",
        "default_plan": "vc2-1c-2gb",
        "cloud_init": "cloud-init-dev.yaml",
        "features": ["docker", "node", "python", "go", "rust", "git", "tmux"],
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
        "cloud_init": "cloud-init-basic.yaml",
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
        # Fallback to basic
        template_path = CLOUD_INIT_DIR / "cloud-init-basic.yaml"
        if not template_path.exists():
            return ""

    content = template_path.read_text()

    # Replace placeholders
    if domain:
        content = content.replace("{{DOMAIN}}", domain)
    content = content.replace("{{DOMAIN}}", "localhost")

    return base64.b64encode(content.encode()).decode()


def get_type_info(instance_type: str) -> dict:
    config = INSTANCE_CONFIGS.get(instance_type, INSTANCE_CONFIGS["custom"])
    return {
        "type": instance_type,
        "description": config["description"],
        "default_plan": config["default_plan"],
        "features": config["features"],
    }
