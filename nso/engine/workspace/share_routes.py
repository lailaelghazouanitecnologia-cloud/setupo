from fastapi import APIRouter, Depends

from nso.shared.deps import require_project, require_user
from nso.shared.auth.resolve import AuthContext
from nso.engine.workspace import share

router = APIRouter()
join_router = APIRouter()


@router.post("/{name}/share")
async def create_share(
    name: str,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
    permissions: str = "read",
    max_uses: int = 0,
    expires_hours: int = 72,
):
    from nso.shared import db
    workspace = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not workspace:
        from nso.shared.errors import NotFoundError
        raise NotFoundError("Workspace", name)

    result = await share.create_share(
        workspace_id=workspace["id"],
        project_id=project_id,
        created_by=auth.user_id,
        permissions=permissions,
        max_uses=max_uses,
        expires_hours=expires_hours,
    )
    return result


@router.get("/{name}/shares")
async def list_shares(
    name: str,
    project_id: str = Depends(require_project),
):
    from nso.shared import db
    workspace = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not workspace:
        from nso.shared.errors import NotFoundError
        raise NotFoundError("Workspace", name)
    return await share.list_shares(workspace["id"])


@router.delete("/{name}/shares/{share_id}")
async def revoke_share(
    name: str,
    share_id: str,
    project_id: str = Depends(require_project),
):
    await share.revoke_share(share_id)
    return {"ok": True}


@join_router.get("/join/{code}")
async def preview_join(code: str):
    return await share.preview_share(code)


@join_router.post("/join/{code}")
async def redeem_join(
    code: str,
    auth: AuthContext = Depends(require_user),
):
    return await share.redeem_share(code, auth.user_id)
