import logging
import secrets
from datetime import datetime, timedelta

from nso.shared import db
from nso.shared.errors import NotFoundError, ConflictError, ValidationError, AuthError

logger = logging.getLogger("nso.workspace.share")

JOIN_CODE_PREFIX = "ws_j_"
MAX_JOIN_CODE_LENGTH = 32


def generate_join_code() -> str:
    return f"{JOIN_CODE_PREFIX}{secrets.token_urlsafe(12)}"


async def create_share(
    workspace_id: str,
    project_id: str,
    created_by: str,
    permissions: str = "read",
    max_uses: int = 0,
    expires_hours: int = 72,
) -> dict:
    if permissions not in ("read", "write", "admin"):
        raise ValidationError("Permissions must be 'read', 'write', or 'admin'")

    workspace = await db.fetch_one("workspaces", id=workspace_id)
    if not workspace:
        raise NotFoundError("Workspace", workspace_id)

    share_id = f"wsh_{secrets.token_hex(12)}"
    join_code = generate_join_code()
    expires_at = None
    if expires_hours > 0:
        expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()

    await db.insert("workspace_shares", {
        "id": share_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "join_code": join_code,
        "permissions": permissions,
        "max_uses": max_uses,
        "uses": 0,
        "created_by": created_by,
        "expires_at": expires_at,
    })

    logger.info("Share created: %s for workspace %s", share_id, workspace_id)
    return {
        "id": share_id,
        "join_code": join_code,
        "permissions": permissions,
        "max_uses": max_uses,
        "expires_at": expires_at,
    }


async def redeem_share(join_code: str, user_id: str) -> dict:
    share = await db.fetch_one("workspace_shares", join_code=join_code)
    if not share:
        raise NotFoundError("Share", join_code)

    if share.get("expires_at"):
        expires = datetime.fromisoformat(share["expires_at"])
        if datetime.utcnow() > expires:
            raise ValidationError("This share link has expired")

    if share["max_uses"] > 0 and share["uses"] >= share["max_uses"]:
        raise ValidationError("This share link has reached its maximum uses")

    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT id FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (share["workspace_id"], user_id),
    )
    if await cursor.fetchone():
        raise ConflictError("You already have access to this workspace")

    member_id = f"wsm_{secrets.token_hex(12)}"
    await db.insert("workspace_members", {
        "id": member_id,
        "workspace_id": share["workspace_id"],
        "user_id": user_id,
        "permissions": share["permissions"],
        "joined_via": share["id"],
    })

    await db.update("workspace_shares", share["id"], {"uses": share["uses"] + 1})

    logger.info("User %s joined workspace %s via share %s", user_id, share["workspace_id"], share["id"])
    return {
        "workspace_id": share["workspace_id"],
        "project_id": share["project_id"],
        "permissions": share["permissions"],
    }


async def preview_share(join_code: str) -> dict:
    share = await db.fetch_one("workspace_shares", join_code=join_code)
    if not share:
        raise NotFoundError("Share", join_code)

    workspace = await db.fetch_one("workspaces", id=share["workspace_id"])
    workspace_name = workspace["name"] if workspace else "unknown"

    expired = False
    if share.get("expires_at"):
        expires = datetime.fromisoformat(share["expires_at"])
        expired = datetime.utcnow() > expires

    return {
        "workspace_name": workspace_name,
        "permissions": share["permissions"],
        "expired": expired,
        "uses_remaining": share["max_uses"] - share["uses"] if share["max_uses"] > 0 else None,
    }


async def list_shares(workspace_id: str) -> list[dict]:
    return await db.fetch_all("workspace_shares", workspace_id=workspace_id)


async def revoke_share(share_id: str):
    share = await db.fetch_one("workspace_shares", id=share_id)
    if not share:
        raise NotFoundError("Share", share_id)
    await db.delete("workspace_shares", share_id)
    logger.info("Share revoked: %s", share_id)
