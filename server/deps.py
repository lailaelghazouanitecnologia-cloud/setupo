"""Shared FastAPI dependencies."""
from fastapi import Depends

from server.auth.middleware import resolve_auth, AuthContext


async def get_auth(auth: AuthContext | None = Depends(resolve_auth)) -> AuthContext:
    """Get the auth context (admin or project-scoped)."""
    return auth


async def require_project(auth: AuthContext = Depends(get_auth)) -> str:
    """Require a project-scoped API key. Returns project_id."""
    return auth.require_project()


async def require_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    """Require admin access."""
    if not auth or not auth.is_admin:
        from fastapi import HTTPException
        raise HTTPException(403, "Admin access required")
    return auth
