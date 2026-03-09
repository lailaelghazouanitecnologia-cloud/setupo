"""Project members service — invite, join, list, update, remove."""

import logging
import secrets
from datetime import datetime, timezone, timedelta

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, ValidationError, NsoError

logger = logging.getLogger("nso.projects.members")

VALID_ROLES = ("owner", "editor", "viewer")


def _gen_id() -> str:
    return f"pm_{secrets.token_hex(8)}"


def _gen_invite_id() -> str:
    return f"pji_{secrets.token_hex(8)}"


def _gen_join_code() -> str:
    return f"pj_{secrets.token_urlsafe(16)}"


async def add_owner(project_id: str, user_id: str):
    """Insert the project creator as owner. Called on project creation."""
    existing = await db.fetch_one("project_members", project_id=project_id, user_id=user_id)
    if existing:
        return existing
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": _gen_id(),
        "project_id": project_id,
        "user_id": user_id,
        "role": "owner",
        "invited_by": "",
        "join_code": "",
        "joined_at": now,
    }
    await db.insert("project_members", data)
    logger.info("Added owner %s to project %s", user_id, project_id)
    return data


async def list_members(project_id: str) -> list[dict]:
    """List all members of a project with user info."""
    members = await db.fetch_all("project_members", project_id=project_id)
    enriched = []
    for m in members:
        user = await db.fetch_one("users", id=m["user_id"])
        enriched.append({
            "id": m["id"],
            "user_id": m["user_id"],
            "role": m["role"],
            "joined_at": m["joined_at"],
            "email": user.get("email", "") if user else "",
            "name": user.get("name", "") if user else "",
        })
    return enriched


async def create_invite(
    project_id: str,
    created_by: str,
    role: str = "viewer",
    max_uses: int = 0,
    expires_hours: int = 0,
) -> dict:
    """Create an invite link for a project."""
    if role not in ("editor", "viewer"):
        raise ValidationError(f"Invite role must be 'editor' or 'viewer', got '{role}'")

    now = datetime.now(timezone.utc)
    expires_at = ""
    if expires_hours > 0:
        expires_at = (now + timedelta(hours=expires_hours)).isoformat()

    code = _gen_join_code()
    data = {
        "id": _gen_invite_id(),
        "project_id": project_id,
        "join_code": code,
        "role": role,
        "max_uses": max_uses,
        "uses": 0,
        "created_by": created_by,
        "expires_at": expires_at,
        "created_at": now.isoformat(),
    }
    await db.insert("project_invites", data)
    logger.info("Created invite %s for project %s (role=%s)", code, project_id, role)
    return data


async def redeem_invite(code: str, user_id: str) -> dict:
    """Redeem a join code and become a project member."""
    invite = await db.fetch_one("project_invites", join_code=code)
    if not invite:
        raise NotFoundError("Invite", code)

    # Check expiry
    if invite.get("expires_at"):
        expires = datetime.fromisoformat(invite["expires_at"])
        if datetime.now(timezone.utc) > expires:
            raise ValidationError("This invite link has expired")

    # Check max uses
    if invite["max_uses"] > 0 and invite["uses"] >= invite["max_uses"]:
        raise ValidationError("This invite link has reached its maximum uses")

    # Check already member
    existing = await db.fetch_one(
        "project_members",
        project_id=invite["project_id"],
        user_id=user_id,
    )
    if existing:
        raise ConflictError("You are already a member of this project")

    # Add member
    now = datetime.now(timezone.utc).isoformat()
    member = {
        "id": _gen_id(),
        "project_id": invite["project_id"],
        "user_id": user_id,
        "role": invite["role"],
        "invited_by": invite["created_by"],
        "join_code": code,
        "joined_at": now,
    }
    await db.insert("project_members", member)

    # Increment uses
    await db.update("project_invites", invite["id"], {"uses": invite["uses"] + 1})

    logger.info("User %s joined project %s via invite %s", user_id, invite["project_id"], code)
    return member


async def preview_invite(code: str) -> dict:
    """Preview an invite without redeeming."""
    invite = await db.fetch_one("project_invites", join_code=code)
    if not invite:
        raise NotFoundError("Invite", code)

    project = await db.fetch_one("projects", id=invite["project_id"])
    expired = False
    if invite.get("expires_at"):
        expires = datetime.fromisoformat(invite["expires_at"])
        expired = datetime.now(timezone.utc) > expires

    uses_remaining = None
    if invite["max_uses"] > 0:
        uses_remaining = max(0, invite["max_uses"] - invite["uses"])

    return {
        "project_name": project["name"] if project else "Unknown",
        "role": invite["role"],
        "expired": expired,
        "uses_remaining": uses_remaining,
    }


async def update_member_role(project_id: str, user_id: str, new_role: str):
    """Change a member's role. Cannot change owner role."""
    if new_role not in VALID_ROLES:
        raise ValidationError(f"Invalid role '{new_role}'. Must be one of: {', '.join(VALID_ROLES)}")

    member = await db.fetch_one("project_members", project_id=project_id, user_id=user_id)
    if not member:
        raise NotFoundError("Member", user_id)

    if member["role"] == "owner":
        raise NsoError("Cannot change the owner's role", 403)

    if new_role == "owner":
        raise NsoError("Cannot promote to owner", 403)

    await db.update("project_members", member["id"], {"role": new_role})
    logger.info("Updated role for user %s in project %s to %s", user_id, project_id, new_role)


async def remove_member(project_id: str, user_id: str):
    """Remove a member from a project. Cannot remove owner."""
    member = await db.fetch_one("project_members", project_id=project_id, user_id=user_id)
    if not member:
        raise NotFoundError("Member", user_id)

    if member["role"] == "owner":
        raise NsoError("Cannot remove the project owner", 403)

    await db.delete("project_members", member["id"])
    logger.info("Removed user %s from project %s", user_id, project_id)


async def list_invites(project_id: str) -> list[dict]:
    """List all invites for a project."""
    return await db.fetch_all("project_invites", project_id=project_id)


async def revoke_invite(invite_id: str):
    """Delete an invite."""
    invite = await db.fetch_one("project_invites", id=invite_id)
    if not invite:
        raise NotFoundError("Invite", invite_id)
    await db.delete("project_invites", invite_id)
    logger.info("Revoked invite %s", invite_id)


async def get_member_role(project_id: str, user_id: str) -> str | None:
    """Get the role of a user in a project, or None if not a member."""
    member = await db.fetch_one("project_members", project_id=project_id, user_id=user_id)
    if not member:
        return None
    return member["role"]
