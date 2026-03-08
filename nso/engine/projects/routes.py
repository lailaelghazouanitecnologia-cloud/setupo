from fastapi import APIRouter, Depends, HTTPException

from nso.shared.models import CreateProjectRequest
from nso.engine.projects import service as pm
from nso.shared import db
from nso.shared.errors import NsoError
from nso.shared.deps import require_admin, require_user, get_auth
from nso.shared.auth.resolve import AuthContext

router = APIRouter()


async def _check_project_access(auth: AuthContext, project_id: str):
    if not auth:
        raise HTTPException(403, "Access denied")
    if auth.is_admin:
        return
    if auth.project_id == project_id:
        return
    # User JWT — check ownership
    if auth.user_id:
        project = await db.fetch_one("projects", id=project_id)
        if project and project.get("owner") == auth.user_id:
            return
    raise HTTPException(403, "Access denied")


@router.post("")
async def create_project(req: CreateProjectRequest, auth: AuthContext = Depends(require_user)):
    if not req.owner and auth.user_id:
        req.owner = auth.user_id
    try:
        project, api_key = await pm.create_project(req)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "owner": project.owner,
            "created_at": project.created_at.isoformat(),
        },
        "api_key": api_key,
        "message": "Save this API key — it won't be shown again.",
    }


@router.get("")
async def list_projects(auth: AuthContext = Depends(require_user)):
    if auth.is_admin:
        projects = await pm.list_projects()
    else:
        # User's own projects + orphan projects (owner="" from before fix)
        owned = await db.fetch_all("projects", owner=auth.user_id)
        d = await db.get_db()
        cursor = await d.execute(
            "SELECT * FROM projects WHERE owner = '' OR owner IS NULL",
        )
        orphans = [db.row_to_dict(dict(r)) for r in await cursor.fetchall()]
        # Auto-claim orphans for this user
        for p in orphans:
            await db.update("projects", p["id"], {"owner": auth.user_id})
        projects = owned + orphans
    return {"projects": [pm._safe_project(p) for p in projects]}


@router.get("/{project_id}")
async def get_project(project_id: str, auth: AuthContext = Depends(require_user)):
    await _check_project_access(auth, project_id)
    try:
        project = await pm.get_project(project_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"project": project}


@router.delete("/{project_id}")
async def delete_project(project_id: str, auth: AuthContext = Depends(require_user)):
    await _check_project_access(auth, project_id)
    try:
        await pm.delete_project(project_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True}


@router.post("/{project_id}/rotate-key")
async def rotate_key(project_id: str, auth: AuthContext = Depends(require_user)):
    await _check_project_access(auth, project_id)
    try:
        new_key = await pm.rotate_api_key(project_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {
        "api_key": new_key,
        "message": "Save this API key — it won't be shown again. Previous key is now invalid.",
    }


@router.put("/{project_id}/settings")
async def update_settings(project_id: str, new_settings: dict, auth: AuthContext = Depends(require_user)):
    await _check_project_access(auth, project_id)
    try:
        await pm.update_project_settings(project_id, new_settings)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"updated": True}
