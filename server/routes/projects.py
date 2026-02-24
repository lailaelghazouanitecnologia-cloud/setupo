"""Project routes — CRUD + API key management."""
from fastapi import APIRouter, Depends

from core.models import CreateProjectRequest
from core.projects import manager as pm
from core.errors import SetupoError
from server.deps import require_admin, require_project, get_auth
from server.auth.middleware import AuthContext

router = APIRouter()


@router.post("")
async def create_project(req: CreateProjectRequest, auth: AuthContext = Depends(get_auth)):
    """Create a new project. Returns the project and API key (shown only once)."""
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
async def list_projects(auth: AuthContext = Depends(require_admin)):
    """List all projects (admin only)."""
    projects = await pm.list_projects()
    return {"projects": projects}


@router.get("/{project_id}")
async def get_project(project_id: str, auth: AuthContext = Depends(get_auth)):
    """Get project details."""
    if auth and not auth.is_admin and auth.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(403, "Access denied")
    project = await pm.get_project(project_id)
    return {"project": project}


@router.delete("/{project_id}")
async def delete_project(project_id: str, auth: AuthContext = Depends(get_auth)):
    """Delete a project and all its resources."""
    if auth and not auth.is_admin and auth.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(403, "Access denied")
    await pm.delete_project(project_id)
    return {"deleted": True}


@router.post("/{project_id}/rotate-key")
async def rotate_key(project_id: str, auth: AuthContext = Depends(get_auth)):
    """Generate a new API key for the project. Old key becomes invalid."""
    if auth and not auth.is_admin and auth.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(403, "Access denied")
    new_key = await pm.rotate_api_key(project_id)
    return {
        "api_key": new_key,
        "message": "Save this API key — it won't be shown again. Previous key is now invalid.",
    }


@router.put("/{project_id}/settings")
async def update_settings(project_id: str, new_settings: dict, auth: AuthContext = Depends(get_auth)):
    """Update project settings (e.g., Cloudflare token)."""
    if auth and not auth.is_admin and auth.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(403, "Access denied")
    await pm.update_project_settings(project_id, new_settings)
    return {"updated": True}
