import logging
import secrets

from fastapi import APIRouter, HTTPException, Depends

from nso.shared import db
from nso.shared.models import CreateDomainRequest
from nso.engine.dns.service import CloudflareProvider
from nso.shared.deps import require_project, require_project_admin

logger = logging.getLogger("nso.domains")
router = APIRouter()


@router.post("", status_code=201, summary="Add domain")
async def create_domain(req: CreateDomainRequest, project_id: str = Depends(require_project_admin)):
    # Block writes on frozen projects + enforce domain limit
    try:
        from nso.engine.billing.service import check_project_not_frozen, check_plan_limit_for_project
        await check_project_not_frozen(project_id)
        current_domains = await db.fetch_all("domains", project_id=project_id)
        await check_plan_limit_for_project(
            project_id, "custom_domains", len(current_domains), "custom domain",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Domain limit/frozen check failed (allowing): %s", e)

    inst = await db.fetch_one("instances", id=req.instance_id)
    if not inst or inst["project_id"] != project_id:
        raise HTTPException(404, "Machine not found")

    ip = inst.get("ip")
    if not ip:
        raise HTTPException(400, "Machine has no IP yet — wait until it's ready")

    domain_id = f"dom_{secrets.token_hex(8)}"
    managed = False
    cf_record_id = None
    cf_zone_id = req.cf_zone_id

    cf_token = req.cf_api_token
    if not cf_token:
        project = await db.fetch_one("projects", id=project_id)
        cf_token = (project.get("settings") or {}).get("cf_api_token")

    if cf_token:
        cf = CloudflareProvider(cf_token)
        try:
            if not cf_zone_id:
                zone = await cf.get_zone_by_domain(req.domain)
                if not zone:
                    raise HTTPException(400, f"Could not find Cloudflare zone for '{req.domain}'. Provide cf_zone_id.")
                cf_zone_id = zone["id"]

            record = await cf.create_dns_record(
                zone_id=cf_zone_id,
                record_type="A",
                name=req.domain,
                content=ip,
                proxied=req.proxied,
            )
            cf_record_id = record.get("id")
            managed = True
            logger.info("Created Cloudflare DNS: %s → %s", req.domain, ip)
        finally:
            await cf.close()

    await db.insert("domains", {
        "id": domain_id,
        "project_id": project_id,
        "instance_id": req.instance_id,
        "domain": req.domain,
        "record_type": "A",
        "value": ip,
        "cf_zone_id": cf_zone_id,
        "cf_record_id": cf_record_id,
        "proxied": req.proxied,
        "managed": managed,
    })

    await db.update("instances", req.instance_id, {"domain": req.domain})

    result = {
        "domain": {
            "id": domain_id,
            "domain": req.domain,
            "ip": ip,
            "managed": managed,
        }
    }

    if not managed:
        result["message"] = f"Point your domain '{req.domain}' to IP {ip} (A record). Provide cf_api_token for auto DNS."
        result["dns_instructions"] = {
            "type": "A",
            "name": req.domain,
            "value": ip,
            "ttl": "auto",
        }

    return result


@router.get("", summary="List domains")
async def list_domains(project_id: str = Depends(require_project)):
    domains = await db.fetch_all("domains", project_id=project_id)
    return {"domains": domains}


@router.delete("/{domain_id}", summary="Remove domain")
async def delete_domain(domain_id: str, project_id: str = Depends(require_project_admin)):
    dom = await db.fetch_one("domains", id=domain_id)
    if not dom or dom["project_id"] != project_id:
        raise HTTPException(404, "Domain not found")

    if dom.get("managed") and dom.get("cf_record_id") and dom.get("cf_zone_id"):
        project = await db.fetch_one("projects", id=project_id)
        cf_token = (project.get("settings") or {}).get("cf_api_token")
        if cf_token:
            cf = CloudflareProvider(cf_token)
            try:
                await cf.delete_dns_record(dom["cf_zone_id"], dom["cf_record_id"])
            except Exception as e:
                logger.warning("Failed to delete CF record: %s", e)
            finally:
                await cf.close()

    await db.delete("domains", domain_id)
    return {"deleted": True}
