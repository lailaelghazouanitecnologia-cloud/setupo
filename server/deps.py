from fastapi import Depends, HTTPException, Request

from server.auth.middleware import resolve_auth, AuthContext


async def get_auth(auth: AuthContext | None = Depends(resolve_auth)) -> AuthContext:
    return auth


async def require_project(request: Request, auth: AuthContext = Depends(get_auth)) -> str:
    if auth.project_id:
        return auth.project_id
    if auth.is_admin:
        project_id = request.path_params.get("project_id")
        if project_id:
            return project_id
        raise HTTPException(400, "Admin request must include project_id in URL")
    raise HTTPException(403, "This endpoint requires a project API key or admin token")


async def require_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.is_admin:
        raise HTTPException(403, "Admin access required")
    return auth


async def require_user(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.user_id:
        raise HTTPException(401, "User authentication required")
    return auth
