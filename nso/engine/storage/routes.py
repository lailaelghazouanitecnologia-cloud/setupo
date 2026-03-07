import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nso.shared import db
from nso.shared.models import ZarUploadResult
from nso.engine.storage.zar_packer import pack, read_manifest
from nso.engine.storage.service import R2Client
from nso.engine.workspace.config import read_config, read_package_config
from nso.config import settings
from nso.shared.deps import require_project
from nso.engine.build.service import (
    compute_source_hash,
    check_cache as check_build_cache,
    execute_build,
)

logger = logging.getLogger("nso.routes.zar")
router = APIRouter()

DEPLOY_TIMEOUT = 300.0
AGENT_AUTH_TIMEOUT = 15.0
ROLLBACK_TIMEOUT = 60.0

# Force IPv4 for all agent connections (IPv6 may not be routable between VPSes)
_ipv4_transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")


def _agent_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=_ipv4_transport)


def _get_r2() -> R2Client:
    cfg = settings.r2_config()
    if not cfg.endpoint:
        raise HTTPException(503, "R2 not configured. Set R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.")
    return R2Client(cfg)


async def _get_agent_url(instance_id: str, project_id: str) -> str:
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst:
        raise HTTPException(404, f"Instance {instance_id} not found")
    if inst.get("project_id") != project_id:
        raise HTTPException(403, "Instance does not belong to this project")

    state = inst.get("state", "")
    if state in ("creating", "installing"):
        raise HTTPException(409, f"Instance is still {state} — wait until it's ready")
    if state == "destroying":
        raise HTTPException(409, "Instance is being destroyed")
    if state == "error":
        raise HTTPException(409, f"Instance in error state: {inst.get('error', 'unknown')}")

    ip = inst.get("ip")
    if not ip:
        raise HTTPException(400, "Instance has no IP address yet")
    return f"http://{ip}:8081"


async def _get_agent_token(agent_url: str) -> str:
    agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")
    if not agent_password:
        raise HTTPException(503, "AGENT_ADMIN_PASSWORD not configured")
    try:
        async with _agent_client(AGENT_AUTH_TIMEOUT) as client:
            resp = await client.post(f"{agent_url}/auth/login", json={
                "email": settings.ADMIN_EMAIL,
                "password": agent_password,
            })
    except httpx.ConnectError:
        raise HTTPException(502, f"Cannot connect to agent at {agent_url}")
    except httpx.TimeoutException:
        raise HTTPException(504, f"Agent at {agent_url} did not respond in time")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Agent connection error: {exc}")

    if resp.status_code != 200:
        raise HTTPException(502, f"Agent auth failed (HTTP {resp.status_code})")
    try:
        return resp.json()["token"]
    except (KeyError, ValueError):
        raise HTTPException(502, "Agent returned invalid auth response")


async def _resolve_instance(name: str, project_id: str, instance_id: str = "") -> str:
    if instance_id:
        return instance_id
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if ws and ws.get("instance_id"):
        return ws["instance_id"]
    if ws:
        config = read_config(ws.get("path", ""))
        if config and config.deploy.instance_id:
            return config.deploy.instance_id
    raise HTTPException(400, "No instance_id specified and none in config.toml")


async def _deploy_via_agent(agent_url: str, token: str, r2_key: str,
                            target_dir: str = "/opt/app", restart_service: str = "",
                            secrets: dict[str, str] | None = None) -> dict:
    r2_cfg = settings.r2_config()
    try:
        async with _agent_client(DEPLOY_TIMEOUT) as client:
            resp = await client.post(
                f"{agent_url}/deploy/pull",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "r2_key": r2_key,
                    "r2_endpoint": r2_cfg.endpoint,
                    "r2_bucket": r2_cfg.bucket,
                    "r2_access_key_id": r2_cfg.access_key_id,
                    "r2_secret_access_key": r2_cfg.secret_access_key,
                    "target_dir": target_dir,
                    "restart_service": restart_service,
                    "install_deps": True,
                    "secrets": secrets or {},
                    "use_pipeline": True,
                },
            )
    except httpx.ConnectError:
        raise HTTPException(502, f"Cannot connect to agent at {agent_url}")
    except httpx.TimeoutException:
        raise HTTPException(504, "Deploy timed out — agent did not respond")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Agent connection error during deploy: {exc}")

    if resp.status_code != 200:
        try:
            body = resp.json()
            detail = body.get("detail", body.get("error", resp.text[:500]))
        except Exception:
            detail = resp.text[:500]
        raise HTTPException(502, f"Agent deploy failed (HTTP {resp.status_code}): {detail}")

    try:
        return resp.json()
    except ValueError:
        raise HTTPException(502, "Agent returned invalid JSON after deploy")


class DeployZarRequest(BaseModel):
    branch: str = "main"
    version: str = ""
    instance_id: str = ""


class ShipRequest(BaseModel):
    branch: str = "main"
    instance_id: str = ""
    domain: str = ""  # optional custom domain; auto-generated if empty


class RollbackRequest(BaseModel):
    instance_id: str
    snapshot: str = ""
    target_dir: str = ""


class BranchRequest(BaseModel):
    name: str
    from_branch: str = "main"


class MergeRequest(BaseModel):
    from_branch: str
    to_branch: str = "main"


class SelfUpdateRequest(BaseModel):
    instance_id: str
    component: str
    r2_key: str = ""


@router.post("/{name}/pack")
async def pack_workspace(name: str, project_id: str = Depends(require_project)):
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if not ws_path:
        raise HTTPException(400, f"Workspace '{name}' has no path configured")

    pkg_config = read_package_config(ws_path)
    try:
        zar_bytes, manifest = pack(
            workspace_path=ws_path,
            version=pkg_config.version if pkg_config else None,
            branch=pkg_config.branch if pkg_config else "main",
            project_id=project_id,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace directory not found: {ws_path}")

    return {"ok": True, "manifest": manifest.model_dump(), "size": len(zar_bytes)}


@router.post("/{name}/push")
async def push_workspace(name: str, branch: str = "main", project_id: str = Depends(require_project)):
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if not ws_path:
        raise HTTPException(400, f"Workspace '{name}' has no path configured")

    pkg_config = read_package_config(ws_path)
    try:
        zar_bytes, manifest = pack(
            workspace_path=ws_path,
            version=pkg_config.version if pkg_config else None,
            branch=branch,
            project_id=project_id,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace directory not found: {ws_path}")

    r2 = _get_r2()
    try:
        key = await r2.upload_zar(project_id, name, branch, manifest.version, zar_bytes)
    except RuntimeError as exc:
        raise HTTPException(502, f"R2 upload failed: {exc}")
    finally:
        await r2.close()

    return ZarUploadResult(
        name=name, version=manifest.version, branch=branch,
        hash=manifest.hash, r2_key=key, size=len(zar_bytes),
    ).model_dump()


@router.post("/{name}/deploy")
async def deploy_zar(name: str, req: DeployZarRequest, project_id: str = Depends(require_project)):
    instance_id = await _resolve_instance(name, project_id, req.instance_id)

    if req.version:
        r2_key = f"{project_id}/{name}/{req.branch}/v{req.version}.zar"
    else:
        r2_key = f"{project_id}/{name}/{req.branch}/latest.zar"

    r2 = _get_r2()
    try:
        if not await r2.exists(r2_key):
            raise HTTPException(404, f"Package not found in R2: {r2_key}. Run /push first.")
    finally:
        await r2.close()

    agent_url = await _get_agent_url(instance_id, project_id)
    token = await _get_agent_token(agent_url)

    # Resolve project secrets
    resolved_secrets: dict[str, str] = {}
    try:
        rows = await db.fetch_all("project_secrets", project_id=project_id)
        for row in rows:
            k = row.get("key", "")
            v = row.get("value", "")
            if k:
                resolved_secrets[k] = v
    except Exception:
        pass

    await db.update("instances", instance_id, {"state": "deploying", "workspace": name})
    try:
        result = await _deploy_via_agent(agent_url, token, r2_key, secrets=resolved_secrets)
    except HTTPException:
        await db.update("instances", instance_id, {"state": "error", "error": "deploy failed"})
        raise

    await db.update("instances", instance_id, {"state": "running", "error": ""})
    return {
        "ok": True, "workspace": name, "branch": req.branch,
        "version": result.get("version", ""), "snapshot": result.get("snapshot", ""),
        "instance_id": instance_id,
        "pipeline": result.get("pipeline", False),
        "phases": result.get("phases", []),
    }


@router.post("/{name}/ship")
async def ship_workspace(name: str, req: ShipRequest, project_id: str = Depends(require_project)):
    ws = await db.fetch_one("workspaces", project_id=project_id, name=name)
    if not ws:
        raise HTTPException(404, f"Workspace '{name}' not found")

    ws_path = ws.get("path", "")
    if not ws_path:
        raise HTTPException(400, f"Workspace '{name}' has no path configured")

    pkg_config = read_package_config(ws_path)
    try:
        zar_bytes, manifest = pack(
            workspace_path=ws_path,
            version=pkg_config.version if pkg_config else None,
            branch=req.branch,
            project_id=project_id,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace directory not found: {ws_path}")

    r2 = _get_r2()
    try:
        r2_key = await r2.upload_zar(project_id, name, req.branch, manifest.version, zar_bytes)
    except RuntimeError as exc:
        raise HTTPException(502, f"R2 upload failed: {exc}")
    finally:
        await r2.close()

    instance_id = await _resolve_instance(name, project_id, req.instance_id)
    agent_url = await _get_agent_url(instance_id, project_id)
    token = await _get_agent_token(agent_url)

    # Resolve project secrets for deploy.toml ${secret:KEY} references
    resolved_secrets: dict[str, str] = {}
    try:
        rows = await db.fetch_all("project_secrets", project_id=project_id)
        for row in rows:
            k = row.get("key", "")
            v = row.get("value", "")
            if k:
                resolved_secrets[k] = v
    except Exception as exc:
        logger.warning("Could not load project secrets: %s", exc)

    # ── Smart Build: check cache / route to server or agent ──
    build_info = {}
    build_command = _detect_build_command(ws_path)
    config = read_config(ws_path)
    stack = config.type if config else ""

    if build_command:
        build_result = await execute_build(
            project_id=project_id,
            workspace=name,
            zar_bytes=zar_bytes,
            build_command=build_command,
            stack=stack,
            secrets=resolved_secrets,
        )
        build_info = {
            "build_strategy": build_result.get("strategy", ""),
            "build_cached": build_result.get("cached", False),
            "build_server": build_result.get("built_on", ""),
            "build_output": build_result.get("output", "")[:500],
        }
        # If server built and artifact cached, pass the artifact R2 key to agent
        if build_result.get("artifact_r2_key"):
            resolved_secrets["__BUILD_ARTIFACT_R2_KEY"] = build_result["artifact_r2_key"]
        logger.info("Build for %s/%s: strategy=%s cached=%s",
                     project_id, name, build_result.get("strategy"), build_result.get("cached"))

    await db.update("instances", instance_id, {"state": "deploying", "workspace": name})
    try:
        result = await _deploy_via_agent(agent_url, token, r2_key, secrets=resolved_secrets)
    except HTTPException:
        await db.update("instances", instance_id, {"state": "error", "error": "ship deploy failed"})
        raise

    await db.update("instances", instance_id, {"state": "running", "error": ""})

    # ── Auto-claim subdomain if user doesn't have one ──
    project = await db.fetch_one("projects", id=project_id)
    owner_id = project.get("owner", "") if project else ""
    if owner_id:
        from nso.engine.deploy_agent.tools import _auto_claim_subdomain
        await _auto_claim_subdomain(owner_id)

    # ── Auto-assign deploy domain ──
    deploy_domain = ""
    dns_error = None
    inst = await db.fetch_one("instances", id=instance_id)
    inst_ip = inst.get("ip", "") if inst else ""

    if inst_ip and settings.CF_API_TOKEN and settings.CF_NSO_ZONE_ID:
        # Determine the deploy subdomain
        if req.domain:
            deploy_domain = req.domain
        else:
            # Get project owner's subdomain for namespacing
            project = await db.fetch_one("projects", id=project_id)
            owner_id = project.get("owner", "") if project else ""
            owner_sub = ""
            if owner_id:
                owner = await db.fetch_one("users", id=owner_id)
                owner_sub = (owner.get("subdomain", "") if owner else "").strip()
            if owner_sub:
                deploy_domain = f"{name}.{owner_sub}.{settings.NSO_BASE_DOMAIN}"
            else:
                # Fallback: workspace-projectshort.nso.dev
                short = project_id.replace("proj_", "")[:8]
                deploy_domain = f"{name}-{short}.{settings.NSO_BASE_DOMAIN}"

        # Create or update DNS A record (proxied via Cloudflare)
        try:
            from nso.engine.dns.service import CloudflareProvider
            cf = CloudflareProvider(settings.CF_API_TOKEN)
            existing = await cf.find_record(settings.CF_NSO_ZONE_ID, deploy_domain, "A")
            if existing:
                await cf.update_dns_record(
                    settings.CF_NSO_ZONE_ID, existing["id"],
                    "A", deploy_domain, inst_ip, proxied=True,
                )
                cf_record_id = existing["id"]
            else:
                record = await cf.create_dns_record(
                    settings.CF_NSO_ZONE_ID, "A", deploy_domain, inst_ip, proxied=True,
                )
                cf_record_id = record.get("id", "")
            await cf.close()

            # Store in domains table
            import uuid
            dom_existing = await db.fetch_one("domains", project_id=project_id, domain=deploy_domain)
            if dom_existing:
                await db.update("domains", dom_existing["id"], {
                    "value": inst_ip, "cf_record_id": cf_record_id,
                    "instance_id": instance_id, "managed": 1,
                })
            else:
                await db.insert("domains", {
                    "id": f"dom_{uuid.uuid4().hex[:16]}",
                    "project_id": project_id,
                    "instance_id": instance_id,
                    "domain": deploy_domain,
                    "record_type": "A",
                    "value": inst_ip,
                    "cf_zone_id": settings.CF_NSO_ZONE_ID,
                    "cf_record_id": cf_record_id,
                    "proxied": 1,
                    "managed": 1,
                })
            logger.info("Deploy domain %s → %s", deploy_domain, inst_ip)
        except Exception as exc:
            logger.warning("Failed to create deploy domain %s: %s", deploy_domain, exc)
            dns_error = str(exc)

    return {
        "ok": True, "action": "ship", "workspace": name,
        "version": manifest.version, "branch": req.branch,
        "hash": manifest.hash, "r2_key": r2_key, "size": len(zar_bytes),
        "instance_id": instance_id, "snapshot": result.get("snapshot", ""),
        "domain": deploy_domain,
        "dns_error": dns_error,
        "pipeline": result.get("pipeline", False),
        "phases": result.get("phases", []),
        "build": build_info,
    }


@router.post("/{name}/rollback")
async def rollback_workspace(name: str, req: RollbackRequest, project_id: str = Depends(require_project)):
    agent_url = await _get_agent_url(req.instance_id, project_id)
    token = await _get_agent_token(agent_url)

    target_dir = req.target_dir or "/opt/app"

    try:
        async with _agent_client(ROLLBACK_TIMEOUT) as client:
            resp = await client.post(
                f"{agent_url}/deploy/rollback",
                headers={"Authorization": f"Bearer {token}"},
                params={"target_dir": target_dir, "restart_service": ""},
                json={"snapshot": req.snapshot},
            )
    except httpx.ConnectError:
        raise HTTPException(502, "Cannot connect to agent")
    except httpx.TimeoutException:
        raise HTTPException(504, "Rollback timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Agent connection error: {exc}")

    if resp.status_code != 200:
        raise HTTPException(502, f"Agent rollback failed: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        raise HTTPException(502, "Agent returned invalid response")


@router.post("/{name}/branch")
async def create_branch(name: str, req: BranchRequest, project_id: str = Depends(require_project)):
    r2 = _get_r2()
    try:
        key = await r2.copy_branch(project_id, name, req.from_branch, req.name)
    finally:
        await r2.close()
    if not key:
        raise HTTPException(404, f"No .zar found on branch '{req.from_branch}' to copy")
    return {"ok": True, "branch": req.name, "from": req.from_branch, "r2_key": key}


@router.post("/{name}/merge")
async def merge_branch(name: str, req: MergeRequest, project_id: str = Depends(require_project)):
    r2 = _get_r2()
    try:
        zar_bytes = await r2.download_zar(project_id, name, req.from_branch)
        if not zar_bytes:
            raise HTTPException(404, f"No .zar on branch '{req.from_branch}'")
        manifest = read_manifest(zar_bytes)
        version = manifest.version if manifest else "0.1.0"
        key = await r2.upload_zar(project_id, name, req.to_branch, version, zar_bytes)
    finally:
        await r2.close()
    return {"ok": True, "merged": f"{req.from_branch} → {req.to_branch}", "version": version, "r2_key": key}


@router.get("/{name}/versions")
async def list_versions(name: str, branch: str = "main", project_id: str = Depends(require_project)):
    r2 = _get_r2()
    try:
        versions = await r2.list_versions(project_id, name, branch)
        branches = await r2.list_branches(project_id, name)
    finally:
        await r2.close()
    return {"workspace": name, "branch": branch, "versions": versions, "branches": branches}


def _detect_build_command(ws_path: str) -> str:
    """Auto-detect build command from workspace files."""
    import json as _json

    checks = [
        ("package.json", "npm run build"),
        ("Makefile", "make build"),
        ("Cargo.toml", "cargo build --release"),
        ("go.mod", "go build -o app ./..."),
    ]

    for filename, command in checks:
        fpath = os.path.join(ws_path, filename)
        if os.path.exists(fpath):
            if filename == "package.json":
                try:
                    with open(fpath) as f:
                        pkg = _json.load(f)
                    if "build" not in pkg.get("scripts", {}):
                        continue
                except Exception:
                    continue
            return command
    return ""


@router.post("/self-update")
async def self_update_instance(req: SelfUpdateRequest, project_id: str = Depends(require_project)):
    r2_cfg = settings.r2_config()
    if not req.r2_key:
        default_keys = {
            "agent": f"{project_id}/_system/agent/main/latest.zar",
            "frontend": f"{project_id}/_system/frontend/main/latest.zar",
            "core": f"{project_id}/_system/core/main/latest.zar",
        }
        req.r2_key = default_keys.get(req.component, "")

    agent_url = await _get_agent_url(req.instance_id, project_id)
    token = await _get_agent_token(agent_url)

    try:
        async with _agent_client(DEPLOY_TIMEOUT) as client:
            resp = await client.post(
                f"{agent_url}/deploy/self-update",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "component": req.component,
                    "r2_key": req.r2_key,
                    "r2_endpoint": r2_cfg.endpoint,
                    "r2_bucket": r2_cfg.bucket,
                    "r2_access_key_id": r2_cfg.access_key_id,
                    "r2_secret_access_key": r2_cfg.secret_access_key,
                },
            )
    except httpx.ConnectError:
        raise HTTPException(502, "Cannot connect to agent")
    except httpx.TimeoutException:
        raise HTTPException(504, "Self-update timed out")
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Agent connection error: {exc}")

    if resp.status_code != 200:
        raise HTTPException(502, f"Self-update failed: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        raise HTTPException(502, "Agent returned invalid response")
