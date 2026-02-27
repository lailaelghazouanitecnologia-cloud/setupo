import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from server.deps import require_user, AuthContext
from server.config import settings
from server.routes.notifications import create_notification
from core import users
from core.errors import SetupoError
from core.providers.cloudflare import CloudflareProvider

logger = logging.getLogger("setupo.subdomain")
router = APIRouter()


class ClaimRequest(BaseModel):
    subdomain: str


@router.get("")
async def get_subdomain(auth: AuthContext = Depends(require_user)):
    try:
        user = await users.get_user(auth.user_id)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)

    sub = user.get("subdomain")
    if not sub:
        return {"subdomain": None, "domain": None}
    return {"subdomain": sub, "domain": f"{sub}.{settings.NSO_BASE_DOMAIN}"}


@router.get("/check")
async def check_availability(name: str = Query(..., min_length=3, max_length=32)):
    try:
        available = await users.check_subdomain_available(name)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)
    sub = name.strip().lower()
    return {
        "subdomain": sub,
        "available": available,
        "domain": f"{sub}.{settings.NSO_BASE_DOMAIN}" if available else None,
    }


@router.post("/claim")
async def claim_subdomain(req: ClaimRequest, auth: AuthContext = Depends(require_user)):
    try:
        sub = await users.claim_subdomain(auth.user_id, req.subdomain)
    except SetupoError as e:
        raise HTTPException(e.status_code, e.message)

    full_domain = f"{sub}.{settings.NSO_BASE_DOMAIN}"

    if settings.CF_API_TOKEN and settings.CF_NSO_ZONE_ID:
        cf = CloudflareProvider(settings.CF_API_TOKEN)
        try:
            await cf.create_dns_record(
                zone_id=settings.CF_NSO_ZONE_ID,
                record_type="CNAME",
                name=full_domain,
                content=settings.NSO_BASE_DOMAIN,
                proxied=True,
            )
            logger.info("DNS CNAME created: %s → %s", full_domain, settings.NSO_BASE_DOMAIN)
        except Exception as e:
            logger.error("DNS creation failed for %s: %s", full_domain, e)
        finally:
            await cf.close()

    await create_notification(
        auth.user_id,
        f"Subdomain active: {full_domain}",
        f"Your free subdomain {full_domain} is now live.",
        "success",
    )

    return {"ok": True, "subdomain": sub, "domain": full_domain}
