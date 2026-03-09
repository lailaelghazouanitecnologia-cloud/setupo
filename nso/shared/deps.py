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
    # Regular user — verify ownership or membership
    if auth.user_id:
        from nso.shared import db
        project = await db.fetch_one("projects", id=project_id)
        if project and project.get("owner") == auth.user_id:
            return project_id
        # Check project membership
        member = await db.fetch_one("project_members", project_id=project_id, user_id=auth.user_id)
        if member:
            return project_id
        raise NsoError("You don't have access to this project", 403)
    raise AuthError("This endpoint requires authentication")


async def require_project_admin(request: Request, auth: AuthContext = Depends(get_auth)) -> str:
    """Requires project admin role — project owner, project admin member, or platform admin."""
    if not auth:
        raise AuthError("Authentication required")
    if auth.project_id:
        return auth.project_id
    project_id = request.path_params.get("project_id")
    if not project_id:
        raise NsoError("Request must include project_id in URL", 400)
    if auth.is_admin:
        return project_id
    if auth.user_id:
        from nso.shared import db
        project = await db.fetch_one("projects", id=project_id)
        if project and project.get("owner") == auth.user_id:
            return project_id
        member = await db.fetch_one("project_members", project_id=project_id, user_id=auth.user_id)
        if member and member.get("role") == "admin":
            return project_id
        raise NsoError("Admin access required for this project", 403)
    raise AuthError("This endpoint requires authentication")


# Alias for backwards compatibility
require_project_owner = require_project_admin


async def require_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.is_admin:
        raise NsoError("Admin access required", 403)
    return auth


async def require_user(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if not auth or not auth.user_id:
        raise AuthError("User authentication required")
    return auth
