import logging
import shutil
from datetime import datetime, timezone

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError
from nso.shared.models import Project, CreateProjectRequest
from nso.shared.auth.keys import generate_api_key, hash_api_key
from nso.config import settings

logger = logging.getLogger("nso.projects")


def _gen_id() -> str:
    import secrets
    return f"proj_{secrets.token_hex(8)}"


async def create_project(req: CreateProjectRequest) -> tuple[Project, str]:
    existing = await db.fetch_all("projects", name=req.name)
    if existing:
        raise ConflictError(f"Project '{req.name}' already exists")

    api_key = generate_api_key()
    project_id = _gen_id()

    project = Project(
        id=project_id,
        name=req.name,
        api_key_hash=hash_api_key(api_key),
        owner=req.owner,
        created_at=datetime.now(timezone.utc),
    )

    await db.insert("projects", {
        "id": project.id,
        "name": project.name,
        "api_key_hash": project.api_key_hash,
        "owner": project.owner,
        "settings": project.settings,
        "created_at": project.created_at,
    })

    project_dir = settings.project_dir(project_id)
    (project_dir / "workspaces").mkdir(exist_ok=True)

    # Sync compute quotas from owner's billing plan
    if req.owner:
        try:
            from nso.engine.compute.quota import sync_plan_to_quotas
            sub = await db.fetch_one("billing_subscriptions", user_id=req.owner, status="active")
            if not sub:
                sub = await db.fetch_one("billing_subscriptions", user_id=req.owner, status="trialing")
            if sub:
                await sync_plan_to_quotas(req.owner, sub["plan_code"])
        except Exception as e:
            logger.warning("Quota sync on project create failed (non-blocking): %s", e)

    # Auto-add creator as owner member
    if req.owner:
        try:
            from nso.engine.projects.members import add_owner
            await add_owner(project_id, req.owner)
        except Exception as e:
            logger.warning("Failed to add owner member (non-blocking): %s", e)

    logger.info("Created project %s (%s)", project.name, project.id)

    return project, api_key


def _safe_project(project: dict) -> dict:
    """Strip sensitive fields from project dict before returning to client."""
    return {k: v for k, v in project.items() if k != "api_key_hash"}


async def get_project(project_id: str) -> dict:
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        raise NotFoundError("Project", project_id)
    return _safe_project(project)


async def list_projects() -> list[dict]:
    projects = await db.fetch_all("projects")
    return [_safe_project(p) for p in projects]


async def delete_project(project_id: str):
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    await db.delete_where("domains", project_id=project_id)
    await db.delete_where("workspaces", project_id=project_id)

    instances = await db.fetch_all("instances", project_id=project_id)
    for inst in instances:
        await db.delete("instances", inst["id"])

    await db.delete("projects", project_id)

    project_dir = settings.project_dir(project_id)
    if project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=True)

    logger.info("Deleted project %s", project_id)


async def rotate_api_key(project_id: str) -> str:
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    new_key = generate_api_key()
    await db.update("projects", project_id, {
        "api_key_hash": hash_api_key(new_key),
    })
    logger.info("Rotated API key for project %s", project_id)
    return new_key


async def update_project_settings(project_id: str, new_settings: dict):
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        raise NotFoundError("Project", project_id)
    merged = {**project.get("settings", {}), **new_settings}
    await db.update("projects", project_id, {"settings": merged})


# ── System project bootstrap ─────────────────────────────────

SYSTEM_PROJECT_NAME = "nso"

# Known NSO infrastructure instances
_SYSTEM_INSTANCES = [
    {
        "label": "nso-main",
        "ip": "65.20.102.242",
        "region": "ewr",
        "plan": "vc2-1c-1gb",
        "provider": "vultr",
        "state": "running",
    },
    {
        "label": "nso-test",
        "ip": "65.20.103.88",
        "region": "ewr",
        "plan": "vc2-1c-1gb",
        "provider": "vultr",
        "state": "running",
    },
]


async def ensure_system_project(owner_id: str) -> dict:
    """Ensure the system 'nso' project exists for the admin.

    Creates the project and pre-registers the known VPS instances
    if they don't already exist. Returns the project dict.
    """
    import secrets as _secrets

    existing = await db.fetch_all("projects", name=SYSTEM_PROJECT_NAME)
    if existing:
        proj = existing[0]
        # Ensure admin owns it
        if proj.get("owner") != owner_id:
            await db.update("projects", proj["id"], {"owner": owner_id})
        await _ensure_system_instances(proj["id"])
        return proj

    # Create the system project
    api_key = generate_api_key()
    project_id = f"proj_{_secrets.token_hex(8)}"

    await db.insert("projects", {
        "id": project_id,
        "name": SYSTEM_PROJECT_NAME,
        "api_key_hash": hash_api_key(api_key),
        "owner": owner_id,
        "settings": {"system": True},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    project_dir = settings.project_dir(project_id)
    (project_dir / "workspaces").mkdir(exist_ok=True)

    await _ensure_system_instances(project_id)
    logger.info("Created system project 'nso' (%s)", project_id)

    return await db.fetch_one("projects", id=project_id)


async def _ensure_system_instances(project_id: str):
    """Register known VPS instances under the system project if missing."""
    import secrets as _secrets

    existing = await db.fetch_all("instances", project_id=project_id)
    existing_ips = {inst.get("ip") for inst in existing}

    for inst_def in _SYSTEM_INSTANCES:
        if inst_def["ip"] in existing_ips:
            continue
        inst_id = f"inst_{_secrets.token_hex(8)}"
        await db.insert("instances", {
            "id": inst_id,
            "project_id": project_id,
            "type": "system",
            "provider": inst_def["provider"],
            "provider_id": "",
            "label": inst_def["label"],
            "region": inst_def["region"],
            "plan": inst_def["plan"],
            "os_id": 2136,
            "ip": inst_def["ip"],
            "domain": "",
            "state": inst_def["state"],
            "ssh_key_id": "",
            "workspace": "",
            "error": "",
            "metadata": "{}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ready_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Registered system instance %s (%s)", inst_def["label"], inst_def["ip"])
