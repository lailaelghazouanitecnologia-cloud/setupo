from fastapi import Depends, HTTPException, Request

from server.auth.middleware import resolve_auth, AuthContext


async def get_auth(auth: AuthContext | None = Depends(resolve_auth)) -> AuthContext:
    return auth


async def require_project(request: Request, auth: AuthContext = Depends(get_auth)) -> str:
    # API key — project_id is embedded
    if auth.project_id:
        return auth.project_id
    # Admin or authenticated user — take project_id from the URL
    project_id = request.path_params.get("project_id")
    if not project_id:
        raise HTTPException(400, "Request must include project_id in URL")
    if auth.is_admin:
        return project_id
    # Regular user — verify ownership
    if auth.user_id:
        from server.core import db
        project = await db.fetch_one("projects", id=project_id)
        if project and project.get("owner") == auth.user_id:
            return project_id
        raise HTTPException(403, "You don't own this project")
    raise HTTPException(403, "This endpoint requires authentication")


async def require_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.is_admin:
        raise HTTPException(403, "Admin access required")
    return auth


async def require_user(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.user_id:
        raise HTTPException(401, "User authentication required")
    return auth
