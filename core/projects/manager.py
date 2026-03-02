import logging
import shutil
from datetime import datetime, timezone

from core import db
from core.errors import NotFoundError, ConflictError
from core.models import Project, CreateProjectRequest
from server.auth.keys import generate_api_key, hash_api_key
from server.config import settings

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
    logger.info("Created project %s (%s)", project.name, project.id)

    return project, api_key


async def get_project(project_id: str) -> dict:
    project = await db.fetch_one("projects", id=project_id)
    if not project:
        raise NotFoundError("Project", project_id)
    return project


async def list_projects() -> list[dict]:
    return await db.fetch_all("projects")


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
