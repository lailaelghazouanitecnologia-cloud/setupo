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
    "supabase": ["url", "anon_key"],
    "s3": ["endpoint", "access_key", "secret_key", "bucket"],
    "slack": ["bot_token"],
    "docker-registry": ["registry_url"],
}

_ALTERNATIVES = {
    "github": [["app_id", "private_key", "installation_id"]],
    "slack": [["webhook_url"]],
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

@router.get("/{connector_id}/status")
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


async def _test_supabase(config: dict) -> dict:
    url = config.get("url", "").rstrip("/")
    key = config.get("anon_key", "")
    if not url or not key:
        return {"ok": False, "message": "url and anon_key are required"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"{url}/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"})
    if resp.status_code in (200, 204):
        return {"ok": True, "message": "Supabase connection verified", "url": url}
    if resp.status_code == 401:
        return {"ok": False, "message": "Invalid anon_key"}
    return {"ok": False, "message": f"Supabase status {resp.status_code}"}


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


async def _test_docker_registry(config: dict) -> dict:
    url = config.get("registry_url", "").rstrip("/")
    if not url:
        return {"ok": False, "message": "registry_url is required"}
    if not url.startswith("http"):
        url = f"https://{url}"
    username = config.get("username", "")
    password = config.get("password", "")
    auth = (username, password) if username and password else None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        try:
            resp = await c.get(f"{url}/v2/", auth=auth)
        except httpx.ConnectError:
            return {"ok": False, "message": f"Cannot connect to {url}"}
    if resp.status_code == 200:
        return {"ok": True, "message": f"Registry at {url} accessible"}
    if resp.status_code == 401:
        return {"ok": False, "message": "Invalid credentials" if username else "Authentication required"}
    return {"ok": False, "message": f"Registry status {resp.status_code}"}


_TESTERS = {
    "github": _test_github, "supabase": _test_supabase, "s3": _test_s3,
    "slack": _test_slack, "docker-registry": _test_docker_registry,
}


@router.post("/{connector_id}/test")
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

@router.get("/github/repos")
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


@router.get("/github/repos/{owner}/{repo}/branches")
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


@router.get("/github/repos/{owner}/{repo}/commits")
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


@router.post("/github/download")
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


@router.post("/slack/send")
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


@router.get("/slack/channels")
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

@router.get("/s3/files")
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


@router.post("/s3/upload")
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


@router.get("/s3/download")
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


@router.delete("/s3/files")
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
#  SUPABASE ACTIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/supabase/tables")
async def supabase_list_tables(project_id: str = Depends(require_project)):
    """List tables in the connected Supabase project."""
    config = await _get_config(project_id, "supabase")
    url = config.get("url", "").rstrip("/")
    key = config.get("anon_key", "")
    service_key = config.get("service_role_key", key)
    if not url or not key:
        raise HTTPException(400, "url and anon_key required")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        # Use PostgREST schema introspection
        resp = await c.get(f"{url}/rest/v1/", headers={
            "apikey": service_key, "Authorization": f"Bearer {service_key}",
        })
    if resp.status_code == 200:
        # OpenAPI spec — extract table names from paths
        try:
            spec = resp.json()
            paths = spec.get("paths", {})
            tables = [p.lstrip("/") for p in paths if p != "/"]
            return {"tables": tables, "count": len(tables)}
        except Exception:
            return {"tables": [], "message": "Connected but could not parse schema"}
    raise HTTPException(resp.status_code, f"Supabase error: {resp.text[:200]}")


class SupabaseQueryRequest(BaseModel):
    table: str
    select: str = "*"
    filters: dict = {}
    limit: int = 50
    order: str = ""


@router.post("/supabase/query")
async def supabase_query(req: SupabaseQueryRequest, project_id: str = Depends(require_project)):
    """Query a Supabase table via PostgREST."""
    config = await _get_config(project_id, "supabase")
    url = config.get("url", "").rstrip("/")
    key = config.get("anon_key", "")
    service_key = config.get("service_role_key", key)
    if not url or not key:
        raise HTTPException(400, "url and anon_key required")

    params = {"select": req.select, "limit": req.limit}
    if req.order:
        params["order"] = req.order
    for col, val in req.filters.items():
        params[col] = f"eq.{val}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"{url}/rest/v1/{req.table}", params=params, headers={
            "apikey": service_key, "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
        })
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Supabase query error: {resp.text[:200]}")
    rows = resp.json()
    return {"rows": rows, "count": len(rows)}


class SupabaseInsertRequest(BaseModel):
    table: str
    data: dict


@router.post("/supabase/insert")
async def supabase_insert(req: SupabaseInsertRequest, project_id: str = Depends(require_project)):
    """Insert a row into a Supabase table."""
    config = await _get_config(project_id, "supabase")
    url = config.get("url", "").rstrip("/")
    key = config.get("anon_key", "")
    service_key = config.get("service_role_key", key)
    if not url or not key:
        raise HTTPException(400, "url and anon_key required")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.post(f"{url}/rest/v1/{req.table}", json=req.data, headers={
            "apikey": service_key, "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json", "Prefer": "return=representation",
        })
    if resp.status_code not in (200, 201):
        raise HTTPException(resp.status_code, f"Insert error: {resp.text[:200]}")
    return {"ok": True, "inserted": resp.json()}


# ═══════════════════════════════════════════════════════════════
#  DOCKER REGISTRY ACTIONS
# ═══════════════════════════════════════════════════════════════

@router.get("/docker-registry/repositories")
async def docker_list_repositories(project_id: str = Depends(require_project)):
    """List repositories in the connected Docker Registry."""
    config = await _get_config(project_id, "docker-registry")
    url = config.get("registry_url", "").rstrip("/")
    if not url:
        raise HTTPException(400, "registry_url not configured")
    if not url.startswith("http"):
        url = f"https://{url}"
    username = config.get("username", "")
    password = config.get("password", "")
    auth = (username, password) if username and password else None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"{url}/v2/_catalog", auth=auth)
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Registry error: {resp.text[:200]}")
    data = resp.json()
    return {"repositories": data.get("repositories", []), "count": len(data.get("repositories", []))}


@router.get("/docker-registry/tags/{repository:path}")
async def docker_list_tags(repository: str, project_id: str = Depends(require_project)):
    """List tags for a repository in the Docker Registry."""
    config = await _get_config(project_id, "docker-registry")
    url = config.get("registry_url", "").rstrip("/")
    if not url:
        raise HTTPException(400, "registry_url not configured")
    if not url.startswith("http"):
        url = f"https://{url}"
    username = config.get("username", "")
    password = config.get("password", "")
    auth = (username, password) if username and password else None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        resp = await c.get(f"{url}/v2/{repository}/tags/list", auth=auth)
    if resp.status_code == 404:
        raise HTTPException(404, f"Repository '{repository}' not found")
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, f"Registry error: {resp.text[:200]}")
    data = resp.json()
    return {"repository": repository, "tags": data.get("tags", [])}
