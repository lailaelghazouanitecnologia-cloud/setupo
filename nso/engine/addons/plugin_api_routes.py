import base64
import hashlib
import logging
import mimetypes
import secrets as stdlib_secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from nso.shared import db
from nso.engine.storage.service import R2Client
from nso.engine.dns.service import CloudflareProvider
from nso.config import settings
from nso.shared.deps import require_project

logger = logging.getLogger("nso.plugin_api")
router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024
STORAGE_PREFIX = "user-files"


def _r2() -> R2Client:
    return R2Client(settings.r2_config())


async def _require_plugin(project_id: str, plugin_id: str):
    plugin = await db.fetch_one("plugins", project_id=project_id, plugin_id=plugin_id)
    if not plugin or not plugin.get("enabled"):
        raise HTTPException(403, f"Plugin '{plugin_id}' is not installed or is disabled")
    return plugin


# ═══════════════════════════════════════════
#  STORAGE PLUGIN
# ═══════════════════════════════════════════

@router.get("/storage/files")
async def list_storage_files(
    prefix: str = "",
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "storage")
    r2 = _r2()
    try:
        r2_prefix = f"{STORAGE_PREFIX}/{project_id}/{prefix}"
        keys = await r2.list_keys(r2_prefix)
        base_len = len(f"{STORAGE_PREFIX}/{project_id}/")
        files = [{"key": k[base_len:], "full_key": k} for k in keys]
        return {"files": files, "count": len(files), "prefix": prefix}
    finally:
        await r2.close()


class UploadRequest(BaseModel):
    path: str
    content: str
    content_type: str = "application/octet-stream"


@router.post("/storage/upload")
async def upload_storage_file(
    req: UploadRequest,
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "storage")

    data = base64.b64decode(req.content)
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024}MB)")

    path = req.path.strip().lstrip("/")
    if not path:
        raise HTTPException(400, "Path is required")

    key = f"{STORAGE_PREFIX}/{project_id}/{path}"
    r2 = _r2()
    try:
        ok = await r2.upload(key, data, content_type=req.content_type)
        if not ok:
            raise HTTPException(500, "Upload failed")
        return {
            "ok": True,
            "path": path,
            "size": len(data),
            "hash": hashlib.sha256(data).hexdigest()[:16],
        }
    finally:
        await r2.close()


@router.get("/storage/download")
async def download_storage_file(
    path: str = Query(...),
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "storage")

    key = f"{STORAGE_PREFIX}/{project_id}/{path.lstrip('/')}"
    r2 = _r2()
    try:
        data = await r2.download(key)
        if data is None:
            raise HTTPException(404, "File not found")
        return {
            "path": path,
            "content": base64.b64encode(data).decode(),
            "size": len(data),
            "content_type": mimetypes.guess_type(path)[0] or "application/octet-stream",
        }
    finally:
        await r2.close()


@router.delete("/storage/files")
async def delete_storage_file(
    path: str = Query(...),
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "storage")

    key = f"{STORAGE_PREFIX}/{project_id}/{path.lstrip('/')}"
    r2 = _r2()
    try:
        ok = await r2.delete(key)
        if not ok:
            raise HTTPException(500, "Delete failed")
        return {"ok": True, "path": path}
    finally:
        await r2.close()


# ═══════════════════════════════════════════
#  LOGS PLUGIN
# ═══════════════════════════════════════════

@router.get("/logs")
async def get_deploy_logs(
    instance_id: str = Query(""),
    level: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "logs")

    d = await db.get_db()
    query = "SELECT * FROM deploy_logs WHERE 1=1"
    params: list = []

    if instance_id:
        instances = await db.fetch_all("instances", project_id=project_id)
        instance_ids = [i["id"] for i in instances]
        if instance_id not in instance_ids:
            raise HTTPException(404, "Instance not found in this project")
        query += " AND instance_id = ?"
        params.append(instance_id)
    else:
        instances = await db.fetch_all("instances", project_id=project_id)
        if instances:
            placeholders = ",".join("?" for _ in instances)
            query += f" AND instance_id IN ({placeholders})"
            params.extend(i["id"] for i in instances)

    if level:
        query += " AND level = ?"
        params.append(level)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor = await d.execute(query, params)
    rows = await cursor.fetchall()
    logs = [dict(r) for r in rows]

    return {"logs": logs, "count": len(logs)}


# ═══════════════════════════════════════════
#  DNS PLUGIN
# ═══════════════════════════════════════════

@router.get("/dns/records")
async def list_dns_records(
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "dns")
    domains = await db.fetch_all("domains", project_id=project_id)
    return {"records": domains, "count": len(domains)}


class CreateDnsRequest(BaseModel):
    instance_id: str
    domain: str
    proxied: bool = False


@router.post("/dns/records")
async def create_dns_record(
    req: CreateDnsRequest,
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "dns")

    inst = await db.fetch_one("instances", id=req.instance_id)
    if not inst or inst["project_id"] != project_id:
        raise HTTPException(404, "Instance not found")
    ip = inst.get("ip")
    if not ip:
        raise HTTPException(400, "Instance has no IP yet")

    domain_id = f"dom_{stdlib_secrets.token_hex(8)}"
    managed = False
    cf_record_id = None
    cf_zone_id = None

    if settings.CF_API_TOKEN:
        cf = CloudflareProvider(settings.CF_API_TOKEN)
        try:
            zone = await cf.get_zone_by_domain(req.domain)
            if zone:
                cf_zone_id = zone["id"]
                record = await cf.create_dns_record(
                    zone_id=cf_zone_id, record_type="A",
                    name=req.domain, content=ip, proxied=req.proxied,
                )
                cf_record_id = record.get("id")
                managed = True
        except Exception as e:
            logger.warning("DNS auto-setup failed: %s", e)
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

    return {
        "ok": True,
        "record": {
            "id": domain_id, "domain": req.domain,
            "ip": ip, "managed": managed,
        },
    }


@router.delete("/dns/records/{domain_id}")
async def delete_dns_record(
    domain_id: str,
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "dns")

    dom = await db.fetch_one("domains", id=domain_id)
    if not dom or dom["project_id"] != project_id:
        raise HTTPException(404, "Domain not found")

    if dom.get("managed") and dom.get("cf_record_id") and dom.get("cf_zone_id"):
        if settings.CF_API_TOKEN:
            cf = CloudflareProvider(settings.CF_API_TOKEN)
            try:
                await cf.delete_dns_record(dom["cf_zone_id"], dom["cf_record_id"])
            except Exception as e:
                logger.warning("Failed to delete CF record: %s", e)
            finally:
                await cf.close()

    await db.delete("domains", domain_id)
    return {"ok": True}


# ═══════════════════════════════════════════
#  MONITORING PLUGIN
# ═══════════════════════════════════════════

@router.get("/monitoring/instances")
async def get_monitoring_data(
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "monitoring")

    instances = await db.fetch_all("instances", project_id=project_id)
    summary = []
    for inst in instances:
        logs = await db.fetch_all("deploy_logs", order_by="id DESC", instance_id=inst["id"])
        recent_errors = [l for l in logs[:50] if l.get("level") == "error"]
        summary.append({
            "id": inst["id"],
            "label": inst.get("label") or inst["id"],
            "ip": inst.get("ip"),
            "state": inst["state"],
            "region": inst.get("region"),
            "created_at": inst.get("created_at"),
            "ready_at": inst.get("ready_at"),
            "total_logs": len(logs),
            "recent_errors": len(recent_errors),
            "last_log": logs[0] if logs else None,
        })

    return {"instances": summary, "count": len(summary)}


# ═══════════════════════════════════════════
#  BACKUPS PLUGIN
# ═══════════════════════════════════════════

@router.get("/backups/list")
async def list_backups(
    project_id: str = Depends(require_project),
):
    await _require_plugin(project_id, "backups")

    r2 = _r2()
    try:
        keys = await r2.list_keys(f"{project_id}/")
        zar_files = [k for k in keys if k.endswith(".zar")]
        backups = []
        for k in zar_files:
            parts = k.replace(f"{project_id}/", "").split("/")
            if len(parts) >= 3:
                backups.append({
                    "key": k,
                    "workspace": parts[0],
                    "branch": parts[1],
                    "file": parts[2],
                })
        return {"backups": backups, "count": len(backups)}
    finally:
        await r2.close()
