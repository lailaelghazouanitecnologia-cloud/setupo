from fastapi import Depends, Request

from nso.shared.auth.resolve import resolve_auth, AuthContext
from nso.shared.errors import AuthError, NsoError


async def get_auth(auth: AuthContext | None = Depends(resolve_auth)) -> AuthContext:
    return auth


async def require_project(request: Request, auth: AuthContext = Depends(get_auth)) -> str:
    if not auth:
        raise AuthError("Authentication required")
    # API key — project_id is embedded
    if auth.project_id:
        return auth.project_id
    # Admin or authenticated user — take project_id from the URL
    project_id = request.path_params.get("project_id")
    if not project_id:
        raise NsoError("Request must include project_id in URL", 400)
    if auth.is_admin:
        return project_id
    # Regular user — verify ownership
    if auth.user_id:
        from nso.shared import db
        project = await db.fetch_one("projects", id=project_id)
        if project and project.get("owner") == auth.user_id:
            return project_id
        raise NsoError("You don't own this project", 403)
    raise AuthError("This endpoint requires authentication")


async def require_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.is_admin:
        raise NsoError("Admin access required", 403)
    return auth


async def require_user(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.user_id:
        raise AuthError("User authentication required")
    return auth
