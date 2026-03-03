from fastapi import APIRouter, Depends, HTTPException

from server.core.models import CreateProjectRequest
from server.core.projects import manager as pm
from server.core import db
from server.deps import require_admin, require_user, get_auth
from server.auth.middleware import AuthContext

router = APIRouter()


def _check_project_access(auth: AuthContext, project_id: str):
    if auth and not auth.is_admin and auth.project_id != project_id:
        raise HTTPException(403, "Access denied")


@router.post("")
async def create_project(req: CreateProjectRequest, auth: AuthContext = Depends(get_auth)):
    project, api_key = await pm.create_project(req)
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
        projects = await db.fetch_all("projects", owner=auth.user_id)
    return {"projects": projects}


@router.get("/{project_id}")
async def get_project(project_id: str, auth: AuthContext = Depends(get_auth)):
    _check_project_access(auth, project_id)
    project = await pm.get_project(project_id)
    return {"project": project}


@router.delete("/{project_id}")
async def delete_project(project_id: str, auth: AuthContext = Depends(get_auth)):
    _check_project_access(auth, project_id)
    await pm.delete_project(project_id)
    return {"deleted": True}


@router.post("/{project_id}/rotate-key")
async def rotate_key(project_id: str, auth: AuthContext = Depends(get_auth)):
    _check_project_access(auth, project_id)
    new_key = await pm.rotate_api_key(project_id)
    return {
        "api_key": new_key,
        "message": "Save this API key — it won't be shown again. Previous key is now invalid.",
    }


@router.put("/{project_id}/settings")
async def update_settings(project_id: str, new_settings: dict, auth: AuthContext = Depends(get_auth)):
    _check_project_access(auth, project_id)
    await pm.update_project_settings(project_id, new_settings)
    return {"updated": True}
