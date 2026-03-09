"""Routes for project members and invites."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from nso.shared.deps import require_user, require_project
from nso.shared.auth.resolve import AuthContext
from nso.shared.errors import NsoError
from nso.shared import db
from nso.engine.projects import members

router = APIRouter()

# Public join routes (user JWT required, no project key)
join_router = APIRouter()


class InviteRequest(BaseModel):
    role: str = "member"
    max_uses: int = 0
    expires_hours: int = 0


class UpdateRoleRequest(BaseModel):
    role: str


# ── Project-scoped routes (require project access) ──


async def _require_member_access(project_id: str, auth: AuthContext, min_role: str = "member"):
    """Check the user is a member of the project with sufficient role."""
    if auth.is_admin:
        return "admin"
    if not auth.user_id:
        raise HTTPException(403, "User authentication required")

    # Check ownership
    project = await db.fetch_one("projects", id=project_id)
    if project and project.get("owner") == auth.user_id:
        return "admin"

    # Check membership
    role = await members.get_member_role(project_id, auth.user_id)
    if not role:
        raise HTTPException(403, "You are not a member of this project")

    role_levels = {"member": 0, "admin": 1}
    if role_levels.get(role, 0) < role_levels.get(min_role, 0):
        raise HTTPException(403, f"Requires at least '{min_role}' role")
    return role


@router.get("", summary="List project members")
async def list_project_members(
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """List all members of this project."""
    await _require_member_access(project_id, auth, "member")
    member_list = await members.list_members(project_id)
    return {"members": member_list}


@router.post("/invite", summary="Create invite link")
async def create_project_invite(
    req: InviteRequest,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Create an invite link. Only owner can invite."""
    await _require_member_access(project_id, auth, "admin")
    try:
        invite = await members.create_invite(
            project_id=project_id,
            created_by=auth.user_id,
            role=req.role,
            max_uses=req.max_uses,
            expires_hours=req.expires_hours,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "invite": invite}


@router.get("/invites", summary="List invite links")
async def list_project_invites(
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """List all invite links. Only owner can see."""
    await _require_member_access(project_id, auth, "admin")
    invites = await members.list_invites(project_id)
    return {"invites": invites}


@router.delete("/invites/{invite_id}", summary="Revoke invite")
async def revoke_project_invite(
    invite_id: str,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Revoke an invite link. Only owner can revoke."""
    await _require_member_access(project_id, auth, "admin")
    try:
        await members.revoke_invite(invite_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.patch("/{user_id}", summary="Update member role")
async def update_member_role(
    user_id: str,
    req: UpdateRoleRequest,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Change a member's role. Only owner can change roles."""
    await _require_member_access(project_id, auth, "admin")
    try:
        await members.update_member_role(project_id, user_id, req.role)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


@router.delete("/{user_id}", summary="Remove member")
async def remove_project_member(
    user_id: str,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Remove a member. Owner can remove anyone; members can leave."""
    caller_role = await _require_member_access(project_id, auth, "member")
    # Members can remove themselves (leave), but only owners can remove others
    if user_id != auth.user_id and caller_role != "admin":
        raise HTTPException(403, "Only the project owner can remove other members")
    try:
        await members.remove_member(project_id, user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ── Public join routes (require user JWT only) ──


@join_router.get("/join/project/{code}", summary="Preview invite")
async def preview_project_invite(code: str):
    """Preview a project invite without redeeming."""
    try:
        info = await members.preview_invite(code)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return info


@join_router.post("/join/project/{code}", summary="Redeem invite")
async def redeem_project_invite(code: str, auth: AuthContext = Depends(require_user)):
    """Redeem a project invite and become a member."""
    try:
        member = await members.redeem_invite(code, auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True, "member": member}
