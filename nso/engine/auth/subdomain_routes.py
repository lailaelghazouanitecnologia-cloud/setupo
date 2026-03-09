import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from nso.shared.deps import require_user, AuthContext
from nso.config import settings
from nso.engine.notifications.routes import create_notification
from nso.engine.auth import service as users
from nso.shared.errors import NsoError
from nso.engine.dns.service import CloudflareProvider

logger = logging.getLogger("nso.subdomain")
router = APIRouter()


class ClaimRequest(BaseModel):
    subdomain: str


@router.get("", summary="Get subdomain")
async def get_subdomain(auth: AuthContext = Depends(require_user)):
    try:
        user = await users.get_user(auth.user_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    sub = user.get("subdomain")
    if not sub:
        return {"subdomain": None, "domain": None}
    return {"subdomain": sub, "domain": f"{sub}.{settings.NSO_BASE_DOMAIN}"}


@router.get("/check", summary="Check availability")
async def check_availability(name: str = Query(..., min_length=3, max_length=32)):
    try:
        available = await users.check_subdomain_available(name)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    sub = name.strip().lower()
    return {
        "subdomain": sub,
        "available": available,
        "domain": f"{sub}.{settings.NSO_BASE_DOMAIN}" if available else None,
    }


@router.post("/claim", summary="Claim subdomain")
async def claim_subdomain(req: ClaimRequest, auth: AuthContext = Depends(require_user)):
    try:
        sub = await users.claim_subdomain(auth.user_id, req.subdomain)
    except NsoError as e:
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
