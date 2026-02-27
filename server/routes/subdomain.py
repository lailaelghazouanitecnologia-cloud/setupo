import logging
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from server.deps import require_user, AuthContext
from server.config import settings
from server.routes.notifications import create_notification
from core import db
from core.providers.cloudflare import CloudflareProvider

logger = logging.getLogger("setupo.subdomain")
router = APIRouter()

SUBDOMAIN_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
RESERVED = frozenset({
    "www", "api", "admin", "app", "mail", "ftp", "ns1", "ns2",
    "agent", "dashboard", "status", "docs", "blog", "help",
    "support", "dev", "staging", "test", "nso",
})


class ClaimRequest(BaseModel):
    subdomain: str


@router.get("")
async def get_subdomain(auth: AuthContext = Depends(require_user)):
    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    sub = user.get("subdomain")
    if not sub:
        return {"subdomain": None, "domain": None}
    return {"subdomain": sub, "domain": f"{sub}.{settings.NSO_BASE_DOMAIN}"}


@router.post("/claim")
async def claim_subdomain(req: ClaimRequest, auth: AuthContext = Depends(require_user)):
    sub = req.subdomain.strip().lower()

    if not SUBDOMAIN_RE.match(sub):
        raise HTTPException(400, "Subdomain must be 3-32 chars: lowercase letters, digits, hyphens. Must start with a letter.")
    if sub in RESERVED:
        raise HTTPException(400, f"'{sub}' is reserved")

    user = await db.fetch_one("users", id=auth.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.get("subdomain"):
        raise HTTPException(409, f"You already have a subdomain: {user['subdomain']}.{settings.NSO_BASE_DOMAIN}")

    d = await db.get_db()
    cursor = await d.execute("SELECT id FROM users WHERE subdomain = ?", (sub,))
    existing = await cursor.fetchone()
    if existing:
        raise HTTPException(409, f"'{sub}' is already taken")

    full_domain = f"{sub}.{settings.NSO_BASE_DOMAIN}"
    cf_record_id = None

    if settings.CF_API_TOKEN and settings.CF_NSO_ZONE_ID:
        cf = CloudflareProvider(settings.CF_API_TOKEN)
        try:
            record = await cf.create_dns_record(
                zone_id=settings.CF_NSO_ZONE_ID,
                record_type="CNAME",
                name=full_domain,
                content=settings.NSO_BASE_DOMAIN,
                proxied=True,
            )
            cf_record_id = record.get("id")
            logger.info("Created DNS CNAME: %s → %s", full_domain, settings.NSO_BASE_DOMAIN)
        except Exception as e:
            logger.error("Failed to create DNS for %s: %s", full_domain, e)
            raise HTTPException(500, f"DNS setup failed: {e}")
        finally:
            await cf.close()

    await db.update("users", auth.user_id, {"subdomain": sub})
    logger.info("Subdomain claimed: %s → %s", auth.user_id, full_domain)

    await create_notification(
        auth.user_id,
        f"Subdomain claimed: {full_domain}",
        f"Your free subdomain {full_domain} is now active.",
        "success",
    )

    return {"ok": True, "subdomain": sub, "domain": full_domain}
