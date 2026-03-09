"""NSO Addons — Connector endpoints: status, real test, and action tools."""

import base64
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project

logger = logging.getLogger("nso.addons.connectors")
router = APIRouter()

_TIMEOUT = 10.0


async def _require_connector(project_id: str, connector_id: str):
    """Check that a connector is installed and enabled."""
    addon = await db.fetch_one("addons", project_id=project_id, addon_id=connector_id, addon_type="connector")
    if not addon or not addon.get("enabled"):
        raise HTTPException(403, f"Connector '{connector_id}' is not installed or is disabled")
    return addon


async def _get_config(project_id: str, connector_id: str) -> dict:
    addon = await _require_connector(project_id, connector_id)
    return addon.get("config", {})


# ── Required fields per connector ──

_REQUIRED = {
    "github": ["token"],
    "s3": ["endpoint", "access_key", "secret_key", "bucket"],
    "slack": ["bot_token"],
    "cloudflare": ["api_token"],
    "r2": ["endpoint", "access_key", "secret_key", "bucket"],
    "vultr": ["api_key"],
    "hetzner": ["api_token"],
    "runpod": ["api_key"],
}

_ALTERNATIVES = {
    "github": [["app_id", "private_key", "installation_id"]],
    "slack": [["webhook_url"]],
    "cloudflare": [["api_key", "email"]],
}


def _check_configured(connector_id: str, config: dict) -> tuple[bool, list[str]]:
    required = _REQUIRED.get(connector_id, [])
    if not required:
        return False, [f"unknown connector: {connector_id}"]

    missing = [f for f in required if not config.get(f)]
    if not missing:
        return True, []

    for alt_fields in _ALTERNATIVES.get(connector_id, []):
        if all(config.get(f) for f in alt_fields):
            return True, []
    return False, missing


def _mask(v) -> str:
    if isinstance(v, str) and len(v) > 8:
        return f"{v[:4]}...{v[-4:]}"
    return v


# ═══════════════════════════════════════════════════════════════
#  STATUS & TEST
# ═══════════════════════════════════════════════════════════════

@router.get("/{connector_id}/status", summary="Get connector status")
async def connector_status(connector_id: str, project_id: str = Depends(require_project)):
    """Get status and masked config of an installed connector."""
    addon = await _require_connector(project_id, connector_id)
    config = addon.get("config", {})
    configured, missing = _check_configured(connector_id, config)

    return {
        "connector_id": connector_id,
        "name": addon["name"],
        "connected": configured,
        "config_keys": {k: _mask(v) for k, v in config.items()},
        "missing_fields": missing,
        "enabled": addon["enabled"],
    }


# ── Real connection testers ──

async def _test_github(config: dict) -> dict:
    token = config.get("token")
    if not token:
        if config.get("app_id"):
            return {"ok": True, "message": "GitHub App configured", "type": "app"}
        return {"ok": False, "message": "No token or app_id configured"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://api.github.com/user", headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
    if resp.status_code == 200:
        d = resp.json()
        return {"ok": True, "message": f"Connected as {d.get('login')}", "user": d.get("login"),
                "scopes": resp.headers.get("x-oauth-scopes", "")}
    if resp.status_code == 401:
        return {"ok": False, "message": "Invalid or expired token"}
    return {"ok": False, "message": f"GitHub API error ({resp.status_code})"}



async def _test_s3(config: dict) -> dict:
    endpoint = config.get("endpoint", "").rstrip("/")
    access_key = config.get("access_key", "")
    secret_key = config.get("secret_key", "")
    bucket = config.get("bucket", "")
    if not all([endpoint, access_key, secret_key, bucket]):
        return {"ok": False, "message": "endpoint, access_key, secret_key, and bucket are required"}

    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    r2 = R2Client(R2Config(bucket=bucket, endpoint=endpoint, access_key_id=access_key, secret_access_key=secret_key))
    try:
        await r2.list_keys("", max_keys=1)
        return {"ok": True, "message": f"S3 bucket '{bucket}' accessible", "bucket": bucket}
    except Exception as e:
        return {"ok": False, "message": f"S3 connection failed: {e}"}
    finally:
        await r2.close()


async def _test_slack(config: dict) -> dict:
    bot_token = config.get("bot_token", "")
    webhook_url = config.get("webhook_url", "")
    if bot_token:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.post("https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {bot_token}"})
        if resp.status_code == 200:
            d = resp.json()
            if d.get("ok"):
                return {"ok": True, "message": f"Workspace '{d.get('team')}'", "team": d.get("team"), "user": d.get("user")}
            return {"ok": False, "message": f"Slack error: {d.get('error')}"}
        return {"ok": False, "message": f"Slack API error ({resp.status_code})"}
    if webhook_url:
        if not webhook_url.startswith("https://hooks.slack.com/"):
            return {"ok": False, "message": "Invalid webhook URL"}
        return {"ok": True, "message": "Webhook URL configured (use bot_token for full validation)"}
    return {"ok": False, "message": "bot_token or webhook_url required"}



async def _test_cloudflare(config: dict) -> dict:
    api_token = config.get("api_token", "")
    api_key = config.get("api_key", "")
    email = config.get("email", "")

    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    elif api_key and email:
        headers["X-Auth-Key"] = api_key
        headers["X-Auth-Email"] = email
    else:
        return {"ok": False, "message": "api_token or (api_key + email) required"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://api.cloudflare.com/client/v4/user/tokens/verify", headers=headers)
    if resp.status_code == 200:
        d = resp.json()
        if d.get("success"):
            return {"ok": True, "message": "Cloudflare connected", "status": d.get("result", {}).get("status", "active")}
        return {"ok": False, "message": f"Cloudflare error: {d.get('errors', [{}])[0].get('message', 'unknown')}"}
    if resp.status_code == 401:
        return {"ok": False, "message": "Invalid or expired token"}
    return {"ok": False, "message": f"Cloudflare API error ({resp.status_code})"}


async def _test_r2(config: dict) -> dict:
    endpoint = config.get("endpoint", "").rstrip("/")
    access_key = config.get("access_key", "")
    secret_key = config.get("secret_key", "")
    bucket = config.get("bucket", "")
    if not all([endpoint, access_key, secret_key, bucket]):
        return {"ok": False, "message": "endpoint, access_key, secret_key, and bucket are required"}

    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    r2 = R2Client(R2Config(bucket=bucket, endpoint=endpoint, access_key_id=access_key, secret_access_key=secret_key))
    try:
        await r2.list_keys("", max_keys=1)
        return {"ok": True, "message": f"R2 bucket '{bucket}' accessible", "bucket": bucket}
    except Exception as e:
        return {"ok": False, "message": f"R2 connection failed: {e}"}
    finally:
        await r2.close()


async def _test_vultr(config: dict) -> dict:
    api_key = config.get("api_key", "")
    if not api_key:
        return {"ok": False, "message": "API key not configured"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://api.vultr.com/v2/account", headers={
            "Authorization": f"Bearer {api_key}",
        })
    if resp.status_code == 200:
        d = resp.json().get("account", {})
        return {"ok": True, "message": f"Connected — {d.get('name', 'Vultr account')}", "balance": d.get("balance", 0)}
    if resp.status_code in (401, 403):
        return {"ok": False, "message": "Invalid or expired API key"}
    return {"ok": False, "message": f"Vultr API error ({resp.status_code})"}


async def _test_hetzner(config: dict) -> dict:
    api_token = config.get("api_token", "")
    if not api_token:
        return {"ok": False, "message": "API token not configured"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://api.hetzner.cloud/v1/servers", headers={
            "Authorization": f"Bearer {api_token}",
        }, params={"per_page": 1})
    if resp.status_code == 200:
        total = resp.json().get("meta", {}).get("pagination", {}).get("total_entries", 0)
        return {"ok": True, "message": f"Connected — {total} server(s)", "servers": total}
    if resp.status_code in (401, 403):
        return {"ok": False, "message": "Invalid or expired API token"}
    return {"ok": False, "message": f"Hetzner API error ({resp.status_code})"}


async def _test_runpod(config: dict) -> dict:
    api_key = config.get("api_key", "")
    if not api_key:
        return {"ok": False, "message": "API key not configured"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.post("https://api.runpod.io/graphql", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, json={"query": "{ myself { id email } }"})
    if resp.status_code == 200:
        d = resp.json()
        me = d.get("data", {}).get("myself", {})
        if me:
            return {"ok": True, "message": f"Connected — {me.get('email', 'RunPod account')}"}
        errors = d.get("errors", [])
        if errors:
            return {"ok": False, "message": errors[0].get("message", "Unknown error")}
    if resp.status_code in (401, 403):
        return {"ok": False, "message": "Invalid or expired API key"}
    return {"ok": False, "message": f"RunPod API error ({resp.status_code})"}


_TESTERS = {
    "github": _test_github, "s3": _test_s3, "slack": _test_slack,
    "cloudflare": _test_cloudflare, "r2": _test_r2,
    "vultr": _test_vultr, "hetzner": _test_hetzner, "runpod": _test_runpod,
}


@router.post("/{connector_id}/test", summary="Test connector")
async def test_connector(connector_id: str, project_id: str = Depends(require_project)):
    """Test connector by making real API calls to the external service."""
    addon = await _require_connector(project_id, connector_id)
    config = addon.get("config", {})

    configured, missing = _check_configured(connector_id, config)
    if not configured:
        return {"ok": False, "message": f"Not configured — missing: {', '.join(missing)}"}

    tester = _TESTERS.get(connector_id)
    if not tester:
        return {"ok": False, "message": f"Unknown connector: {connector_id}"}
    try:
        result = await tester(config)
    except httpx.TimeoutException:
        result = {"ok": False, "message": f"Timed out after {_TIMEOUT}s"}
    except Exception as e:
        logger.warning("Connector test failed for %s: %s", connector_id, e)
        result = {"ok": False, "message": f"Connection error: {e}"}
    result["connector_id"] = connector_id
    return result


# ═══════════════════════════════════════════════════════════════
#  GITHUB ACTIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/github/repos", summary="List GitHub repos")
async def github_list_repos(
    project_id: str = Depends(require_project),
    per_page: int = Query(30, ge=1, le=100),
    page: int = Query(1, ge=1),
):
    """List repositories accessible with the configured GitHub token."""
    config = await _get_config(project_id, "github")
    token = config.get("token", "")
    if not token:
        raise HTTPException(400, "GitHub token not configured")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://api.github.com/user/repos", params={
            "per_page": per_page, "page": page, "sort": "updated",
        }, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        })
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"GitHub API error: {resp.text[:200]}")
    repos = resp.json()
    return {"repos": [{"full_name": r["full_name"], "private": r["private"],
                        "default_branch": r["default_branch"], "url": r["html_url"],
                        "updated_at": r["updated_at"]} for r in repos], "count": len(repos)}


@router.get("/github/repos/{owner}/{repo}/branches", summary="List repo branches")
async def github_list_branches(owner: str, repo: str, project_id: str = Depends(require_project)):
    """List branches for a GitHub repository."""
    config = await _get_config(project_id, "github")
    token = config.get("token", "")
    if not token:
        raise HTTPException(400, "GitHub token not configured")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"https://api.github.com/repos/{owner}/{repo}/branches",
                           params={"per_page": 100},
                           headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"GitHub API error: {resp.text[:200]}")
    return {"branches": [{"name": b["name"], "sha": b["commit"]["sha"]} for b in resp.json()]}


@router.get("/github/repos/{owner}/{repo}/commits", summary="List repo commits")
async def github_list_commits(
    owner: str, repo: str,
    branch: str = Query(""),
    per_page: int = Query(10, ge=1, le=100),
    project_id: str = Depends(require_project),
):
    """List recent commits for a GitHub repository."""
    config = await _get_config(project_id, "github")
    token = config.get("token", "")
    if not token:
        raise HTTPException(400, "GitHub token not configured")
    params = {"per_page": per_page}
    if branch:
        params["sha"] = branch
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"https://api.github.com/repos/{owner}/{repo}/commits",
                           params=params,
                           headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"GitHub API error: {resp.text[:200]}")
    return {"commits": [{"sha": cm["sha"][:8], "message": cm["commit"]["message"].split("\n")[0],
                          "author": cm["commit"]["author"]["name"],
                          "date": cm["commit"]["author"]["date"]} for cm in resp.json()]}


class GitHubDownloadRequest(BaseModel):
    owner: str
    repo: str
    ref: str = "main"
    path: str = ""


@router.post("/github/download", summary="Download GitHub file")
async def github_download_file(req: GitHubDownloadRequest, project_id: str = Depends(require_project)):
    """Download a file from a GitHub repository."""
    config = await _get_config(project_id, "github")
    token = config.get("token", "")
    if not token:
        raise HTTPException(400, "GitHub token not configured")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(
            f"https://api.github.com/repos/{req.owner}/{req.repo}/contents/{req.path}",
            params={"ref": req.ref},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
    if resp.status_code == 404:
        raise HTTPException(404, "File not found")
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"GitHub API error: {resp.text[:200]}")
    data = resp.json()
    if isinstance(data, list):
        return {"type": "directory", "files": [{"name": f["name"], "type": f["type"], "size": f.get("size", 0)} for f in data]}
    return {"type": "file", "name": data["name"], "size": data.get("size", 0),
            "content": data.get("content", ""), "encoding": data.get("encoding", "base64")}


# ═══════════════════════════════════════════════════════════════
#  SLACK ACTIONS
# ═══════════════════════════════════════════════════════════════

class SlackMessageRequest(BaseModel):
    channel: str = ""
    text: str
    blocks: Optional[list] = None


@router.post("/slack/send", summary="Send Slack message")
async def slack_send_message(req: SlackMessageRequest, project_id: str = Depends(require_project)):
    """Send a message to a Slack channel or webhook."""
    config = await _get_config(project_id, "slack")
    bot_token = config.get("bot_token", "")
    webhook_url = config.get("webhook_url", "")

    if bot_token and req.channel:
        payload = {"channel": req.channel, "text": req.text}
        if req.blocks:
            payload["blocks"] = req.blocks
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.post("https://slack.com/api/chat.postMessage",
                                json=payload,
                                headers={"Authorization": f"Bearer {bot_token}"})
        if resp.status_code != 200:
            raise HTTPException(502, f"Slack API error ({resp.status_code})")
        d = resp.json()
        if not d.get("ok"):
            raise HTTPException(400, f"Slack error: {d.get('error')}")
        return {"ok": True, "ts": d.get("ts"), "channel": d.get("channel")}

    elif webhook_url:
        payload = {"text": req.text}
        if req.blocks:
            payload["blocks"] = req.blocks
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.post(webhook_url, json=payload)
        if resp.status_code != 200:
            raise HTTPException(502, f"Slack webhook error ({resp.status_code}): {resp.text[:100]}")
        return {"ok": True, "method": "webhook"}

    raise HTTPException(400, "bot_token + channel or webhook_url required")


@router.get("/slack/channels", summary="List Slack channels")
async def slack_list_channels(project_id: str = Depends(require_project)):
    """List Slack channels the bot has access to."""
    config = await _get_config(project_id, "slack")
    bot_token = config.get("bot_token", "")
    if not bot_token:
        raise HTTPException(400, "bot_token not configured (required for listing channels)")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://slack.com/api/conversations.list",
                           params={"types": "public_channel,private_channel", "limit": 200},
                           headers={"Authorization": f"Bearer {bot_token}"})
    if resp.status_code != 200:
        raise HTTPException(502, f"Slack API error ({resp.status_code})")
    d = resp.json()
    if not d.get("ok"):
        raise HTTPException(400, f"Slack error: {d.get('error')}")
    return {"channels": [{"id": ch["id"], "name": ch["name"],
                           "is_private": ch.get("is_private", False)} for ch in d.get("channels", [])]}


# ═══════════════════════════════════════════════════════════════
#  S3 ACTIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/s3/files", summary="List S3 files")
async def s3_list_files(
    prefix: str = Query(""),
    project_id: str = Depends(require_project),
):
    """List files in the configured S3 bucket."""
    config = await _get_config(project_id, "s3")
    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    r2 = R2Client(R2Config(
        bucket=config["bucket"], endpoint=config["endpoint"],
        access_key_id=config["access_key"], secret_access_key=config["secret_key"],
    ))
    try:
        keys = await r2.list_keys(prefix)
        return {"files": [{"key": k} for k in keys], "count": len(keys)}
    finally:
        await r2.close()


class S3UploadRequest(BaseModel):
    key: str
    content: str  # base64
    content_type: str = "application/octet-stream"


@router.post("/s3/upload", summary="Upload S3 file")
async def s3_upload_file(req: S3UploadRequest, project_id: str = Depends(require_project)):
    """Upload a file to the configured S3 bucket."""
    config = await _get_config(project_id, "s3")
    data = base64.b64decode(req.content)
    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    r2 = R2Client(R2Config(
        bucket=config["bucket"], endpoint=config["endpoint"],
        access_key_id=config["access_key"], secret_access_key=config["secret_key"],
    ))
    try:
        ok = await r2.upload(req.key, data, content_type=req.content_type)
        if not ok:
            raise HTTPException(502, "S3 upload failed")
        return {"ok": True, "key": req.key, "size": len(data)}
    finally:
        await r2.close()


@router.get("/s3/download", summary="Download S3 file")
async def s3_download_file(key: str = Query(...), project_id: str = Depends(require_project)):
    """Download a file from the configured S3 bucket."""
    config = await _get_config(project_id, "s3")
    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    r2 = R2Client(R2Config(
        bucket=config["bucket"], endpoint=config["endpoint"],
        access_key_id=config["access_key"], secret_access_key=config["secret_key"],
    ))
    try:
        data = await r2.download(key)
        if data is None:
            raise HTTPException(404, "File not found")
        return {"key": key, "content": base64.b64encode(data).decode(), "size": len(data)}
    finally:
        await r2.close()


@router.delete("/s3/files", summary="Delete S3 file")
async def s3_delete_file(key: str = Query(...), project_id: str = Depends(require_project)):
    """Delete a file from the configured S3 bucket."""
    config = await _get_config(project_id, "s3")
    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    r2 = R2Client(R2Config(
        bucket=config["bucket"], endpoint=config["endpoint"],
        access_key_id=config["access_key"], secret_access_key=config["secret_key"],
    ))
    try:
        ok = await r2.delete(key)
        if not ok:
            raise HTTPException(502, "S3 delete failed")
        return {"ok": True, "key": key}
    finally:
        await r2.close()


# ═══════════════════════════════════════════════════════════════
#  CLOUDFLARE ACTIONS
# ═══════════════════════════════════════════════════════════════

def _cf_headers(config: dict) -> dict:
    """Build Cloudflare API headers from connector config."""
    api_token = config.get("api_token", "")
    if api_token:
        return {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    return {
        "X-Auth-Key": config.get("api_key", ""),
        "X-Auth-Email": config.get("email", ""),
        "Content-Type": "application/json",
    }


@router.get("/cloudflare/zones", summary="List Cloudflare zones")
async def cloudflare_list_zones(project_id: str = Depends(require_project)):
    """List DNS zones (domains) in the Cloudflare account."""
    config = await _get_config(project_id, "cloudflare")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get("https://api.cloudflare.com/client/v4/zones",
                           params={"per_page": 50, "status": "active"},
                           headers=_cf_headers(config))
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Cloudflare API error: {resp.text[:300]}")
    d = resp.json()
    if not d.get("success"):
        raise HTTPException(400, f"Cloudflare error: {d.get('errors', [{}])[0].get('message', 'unknown')}")
    return {"zones": [{"id": z["id"], "name": z["name"], "status": z["status"],
                        "name_servers": z.get("name_servers", [])} for z in d.get("result", [])]}


@router.get("/cloudflare/zones/{zone_id}/records", summary="List zone DNS records")
async def cloudflare_list_records(
    zone_id: str,
    name: str = Query(""),
    record_type: str = Query(""),
    project_id: str = Depends(require_project),
):
    """List DNS records in a Cloudflare zone."""
    config = await _get_config(project_id, "cloudflare")
    params: dict = {"per_page": 100}
    if name:
        params["name"] = name
    if record_type:
        params["type"] = record_type
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                           params=params, headers=_cf_headers(config))
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Cloudflare API error: {resp.text[:300]}")
    d = resp.json()
    if not d.get("success"):
        raise HTTPException(400, f"Cloudflare error: {d.get('errors', [{}])[0].get('message', 'unknown')}")
    return {"records": [{"id": r["id"], "type": r["type"], "name": r["name"],
                          "content": r["content"], "proxied": r.get("proxied", False),
                          "ttl": r.get("ttl", 1)} for r in d.get("result", [])]}


class CloudflareDNSRequest(BaseModel):
    zone_id: str
    record_type: str = "A"
    name: str
    content: str
    proxied: bool = True
    ttl: int = 1


@router.post("/cloudflare/records", summary="Create DNS record")
async def cloudflare_create_record(req: CloudflareDNSRequest, project_id: str = Depends(require_project)):
    """Create a DNS record via user's Cloudflare connector."""
    config = await _get_config(project_id, "cloudflare")
    payload = {"type": req.record_type, "name": req.name, "content": req.content,
               "proxied": req.proxied, "ttl": req.ttl}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.post(f"https://api.cloudflare.com/client/v4/zones/{req.zone_id}/dns_records",
                            json=payload, headers=_cf_headers(config))
    if resp.status_code not in (200, 201):
        raise HTTPException(resp.status_code, f"Cloudflare error: {resp.text[:300]}")
    d = resp.json()
    if not d.get("success"):
        raise HTTPException(400, f"Cloudflare error: {d.get('errors', [{}])[0].get('message', 'unknown')}")
    r = d.get("result", {})
    return {"ok": True, "record": {"id": r["id"], "type": r["type"], "name": r["name"],
                                    "content": r["content"], "proxied": r.get("proxied")}}


class CloudflareDNSUpdateRequest(BaseModel):
    zone_id: str
    record_id: str
    record_type: str = "A"
    name: str = ""
    content: str = ""
    proxied: Optional[bool] = None
    ttl: int = 1


@router.patch("/cloudflare/records", summary="Update DNS record")
async def cloudflare_update_record(req: CloudflareDNSUpdateRequest, project_id: str = Depends(require_project)):
    """Update a DNS record via user's Cloudflare connector."""
    config = await _get_config(project_id, "cloudflare")
    payload: dict = {"type": req.record_type, "ttl": req.ttl}
    if req.name:
        payload["name"] = req.name
    if req.content:
        payload["content"] = req.content
    if req.proxied is not None:
        payload["proxied"] = req.proxied
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.patch(f"https://api.cloudflare.com/client/v4/zones/{req.zone_id}/dns_records/{req.record_id}",
                             json=payload, headers=_cf_headers(config))
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Cloudflare error: {resp.text[:300]}")
    d = resp.json()
    if not d.get("success"):
        raise HTTPException(400, f"Cloudflare error: {d.get('errors', [{}])[0].get('message', 'unknown')}")
    return {"ok": True, "updated": req.record_id}


@router.delete("/cloudflare/records", summary="Delete DNS record")
async def cloudflare_delete_record(
    zone_id: str = Query(...),
    record_id: str = Query(...),
    project_id: str = Depends(require_project),
):
    """Delete a DNS record via user's Cloudflare connector."""
    config = await _get_config(project_id, "cloudflare")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.delete(f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                              headers=_cf_headers(config))
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Cloudflare error: {resp.text[:300]}")
    return {"ok": True, "deleted": record_id}


# ═══════════════════════════════════════════════════════════════
#  R2 ACTIONS (Cloudflare R2 — separate from generic S3)
# ═══════════════════════════════════════════════════════════════

def _r2_client(config: dict):
    from nso.shared.models import R2Config
    from nso.engine.storage.service import R2Client
    return R2Client(R2Config(
        bucket=config["bucket"], endpoint=config["endpoint"],
        access_key_id=config["access_key"], secret_access_key=config["secret_key"],
    ))


@router.get("/r2/files", summary="List R2 files")
async def r2_list_files(prefix: str = Query(""), project_id: str = Depends(require_project)):
    """List files in the configured R2 bucket."""
    config = await _get_config(project_id, "r2")
    r2 = _r2_client(config)
    try:
        keys = await r2.list_keys(prefix)
        return {"files": [{"key": k} for k in keys], "count": len(keys)}
    finally:
        await r2.close()


class R2UploadRequest(BaseModel):
    key: str
    content: str  # base64
    content_type: str = "application/octet-stream"


@router.post("/r2/upload", summary="Upload R2 file")
async def r2_upload_file(req: R2UploadRequest, project_id: str = Depends(require_project)):
    """Upload a file to the configured R2 bucket."""
    config = await _get_config(project_id, "r2")
    data = base64.b64decode(req.content)
    r2 = _r2_client(config)
    try:
        ok = await r2.upload(req.key, data, content_type=req.content_type)
        if not ok:
            raise HTTPException(502, "R2 upload failed")
        return {"ok": True, "key": req.key, "size": len(data)}
    finally:
        await r2.close()


@router.get("/r2/download", summary="Download R2 file")
async def r2_download_file(key: str = Query(...), project_id: str = Depends(require_project)):
    """Download a file from the configured R2 bucket."""
    config = await _get_config(project_id, "r2")
    r2 = _r2_client(config)
    try:
        data = await r2.download(key)
        if data is None:
            raise HTTPException(404, "File not found")
        return {"key": key, "content": base64.b64encode(data).decode(), "size": len(data)}
    finally:
        await r2.close()


@router.delete("/r2/files", summary="Delete R2 file")
async def r2_delete_file(key: str = Query(...), project_id: str = Depends(require_project)):
    """Delete a file from the configured R2 bucket."""
    config = await _get_config(project_id, "r2")
    r2 = _r2_client(config)
    try:
        ok = await r2.delete(key)
        if not ok:
            raise HTTPException(502, "R2 delete failed")
        return {"ok": True, "key": key}
    finally:
        await r2.close()


