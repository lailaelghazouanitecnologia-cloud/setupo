import logging
import secrets as stdlib_secrets

from fastapi import APIRouter, HTTPException, Depends

from server.deps import require_user, require_admin, AuthContext
from core import db

logger = logging.getLogger("setupo.notifications")
router = APIRouter()

MAX_NOTIFICATIONS_PER_PAGE = 100


@router.get("")
async def list_notifications(auth: AuthContext = Depends(require_user)):
    items = await db.fetch_all("notifications", user_id=auth.user_id)
    unread = sum(1 for n in items if not n.get("read"))
    return {"notifications": items, "count": len(items), "unread": unread}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, auth: AuthContext = Depends(require_user)):
    notif = await db.fetch_one("notifications", id=notification_id)
    if not notif or notif["user_id"] != auth.user_id:
        raise HTTPException(404, "Notification not found")
    await db.update("notifications", notification_id, {"read": 1})
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(auth: AuthContext = Depends(require_user)):
    d = await db.get_db()
    await d.execute(
        "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
        (auth.user_id,),
    )
    await d.commit()
    return {"ok": True}


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str, auth: AuthContext = Depends(require_user)):
    notif = await db.fetch_one("notifications", id=notification_id)
    if not notif or notif["user_id"] != auth.user_id:
        raise HTTPException(404, "Notification not found")
    await db.delete("notifications", notification_id)
    return {"ok": True}


async def create_notification(user_id: str, title: str, message: str = "", notif_type: str = "info"):
    notif_id = f"notif_{stdlib_secrets.token_hex(12)}"
    await db.insert("notifications", {
        "id": notif_id,
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "read": 0,
    })
    logger.info("Notification for %s: %s", user_id, title)
    return notif_id


@router.post("")
async def send_notification(
    user_id: str,
    title: str,
    message: str = "",
    notif_type: str = "info",
    auth: AuthContext = Depends(require_admin),
):
    notif_id = await create_notification(user_id, title, message, notif_type)
    return {"ok": True, "id": notif_id}
