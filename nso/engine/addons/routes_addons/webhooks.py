"""NSO GitHub Webhook — receives push events and triggers auto-deploy via ship pipeline."""

import hashlib
import hmac
import logging
import secrets as token_gen
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project, require_admin

logger = logging.getLogger("nso.webhooks.github")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK CONFIG MANAGEMENT (authenticated)
# ═══════════════════════════════════════════════════════════════

class CreateWebhookRequest(BaseModel):
    workspace_name: str
    github_repo: str  # "owner/repo"
    github_branch: str = "main"
    instance_id: str = ""


class UpdateWebhookRequest(BaseModel):
    enabled: bool | None = None
    instance_id: str | None = None
    github_branch: str | None = None
    auto_deploy: bool | None = None


@router.get("", summary="List webhooks")
async def list_webhooks(project_id: str = Depends(require_project)):
    """List all webhook configs for a project."""
    webhooks = await db.fetch_all("webhook_configs", project_id=project_id)
    # Mask secrets in response
    for w in webhooks:
        if w.get("secret"):
            w["secret"] = w["secret"][:6] + "..."
    return {"webhooks": webhooks, "count": len(webhooks)}


@router.post("", summary="Create webhook")
async def create_webhook(req: CreateWebhookRequest, project_id: str = Depends(require_project)):
    """Create a webhook config. Returns the secret and the URL to configure in GitHub."""
    # Validate workspace exists
    ws = await db.fetch_one("workspaces", project_id=project_id, name=req.workspace_name)
    if not ws:
        raise HTTPException(404, f"Workspace '{req.workspace_name}' not found")

    # Validate repo format
    if "/" not in req.github_repo or len(req.github_repo.split("/")) != 2:
        raise HTTPException(400, "github_repo must be 'owner/repo' format")

    # Check for duplicate
    existing = await db.fetch_one(
        "webhook_configs", project_id=project_id,
        github_repo=req.github_repo, github_branch=req.github_branch,
    )
    if existing:
        raise HTTPException(409, f"Webhook already exists for {req.github_repo}:{req.github_branch}")

    webhook_id = f"wh_{token_gen.token_hex(8)}"
    secret = token_gen.token_hex(32)  # 64-char hex secret for HMAC

    data = {
        "id": webhook_id,
        "project_id": project_id,
        "workspace_name": req.workspace_name,
        "instance_id": req.instance_id,
        "github_repo": req.github_repo,
        "github_branch": req.github_branch,
        "secret": secret,
        "enabled": True,
        "auto_deploy": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("webhook_configs", data)

    # Build the webhook URL GitHub should POST to
    webhook_url = f"/api/projects/{project_id}/webhooks/github/receive"

    return {
        "ok": True,
        "webhook": {
            "id": webhook_id,
            "workspace_name": req.workspace_name,
            "github_repo": req.github_repo,
            "github_branch": req.github_branch,
        },
        "secret": secret,
        "webhook_url": webhook_url,
        "setup_instructions": {
            "1": f"Go to https://github.com/{req.github_repo}/settings/hooks/new",
            "2": f"Set Payload URL to: https://nso.dev{webhook_url}",
            "3": "Set Content type to: application/json",
            "4": f"Set Secret to: {secret}",
            "5": "Select 'Just the push event'",
            "6": "Click 'Add webhook'",
        },
    }


@router.patch("/{webhook_id}", summary="Update webhook")
async def update_webhook(webhook_id: str, req: UpdateWebhookRequest, project_id: str = Depends(require_project)):
    """Update a webhook config."""
    wh = await db.fetch_one("webhook_configs", id=webhook_id)
    if not wh or wh["project_id"] != project_id:
        raise HTTPException(404, "Webhook not found")

    updates = {}
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    if req.instance_id is not None:
        updates["instance_id"] = req.instance_id
    if req.github_branch is not None:
        updates["github_branch"] = req.github_branch
    if req.auto_deploy is not None:
        updates["auto_deploy"] = req.auto_deploy

    if updates:
        await db.update("webhook_configs", webhook_id, updates)
    return {"ok": True, "updated": list(updates.keys())}


@router.delete("/{webhook_id}", summary="Delete webhook")
async def delete_webhook(webhook_id: str, project_id: str = Depends(require_project)):
    """Delete a webhook config and its delivery history."""
    wh = await db.fetch_one("webhook_configs", id=webhook_id)
    if not wh or wh["project_id"] != project_id:
        raise HTTPException(404, "Webhook not found")

    d = await db.get_db()
    await d.execute("DELETE FROM webhook_deliveries WHERE webhook_id = ?", [webhook_id])
    await d.commit()
    await db.delete("webhook_configs", webhook_id)
    return {"ok": True}


@router.post("/{webhook_id}/rotate-secret", summary="Rotate webhook secret")
async def rotate_webhook_secret(webhook_id: str, project_id: str = Depends(require_project)):
    """Rotate the HMAC secret. Returns new secret — update it in GitHub settings."""
    wh = await db.fetch_one("webhook_configs", id=webhook_id)
    if not wh or wh["project_id"] != project_id:
        raise HTTPException(404, "Webhook not found")

    new_secret = token_gen.token_hex(32)
    await db.update("webhook_configs", webhook_id, {"secret": new_secret})
    return {"ok": True, "secret": new_secret, "note": "Update this secret in your GitHub webhook settings"}


@router.get("/{webhook_id}/deliveries", summary="List deliveries")
async def list_deliveries(
    webhook_id: str,
    limit: int = Query(50, ge=1, le=200),
    project_id: str = Depends(require_project),
):
    """List recent webhook deliveries."""
    wh = await db.fetch_one("webhook_configs", id=webhook_id)
    if not wh or wh["project_id"] != project_id:
        raise HTTPException(404, "Webhook not found")

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM webhook_deliveries WHERE webhook_id = ? ORDER BY id DESC LIMIT ?",
        [webhook_id, limit],
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    return {"deliveries": rows, "count": len(rows)}


# ═══════════════════════════════════════════════════════════════
#  GITHUB WEBHOOK RECEIVER (public — validated by HMAC)
# ═══════════════════════════════════════════════════════════════

def _verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/receive", summary="Receive GitHub webhook")
async def receive_github_webhook(request: Request):
    """
    GitHub webhook receiver. Validates HMAC signature, matches repo/branch
    to a webhook config, and triggers the ship pipeline.

    This endpoint is PUBLIC — authentication is via GitHub's HMAC signature.
    """
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    event_type = request.headers.get("x-github-event", "")
    delivery_id = request.headers.get("x-github-delivery", "")

    # Only handle push events
    if event_type == "ping":
        return {"ok": True, "message": "Pong — webhook configured successfully"}

    if event_type != "push":
        return {"ok": True, "message": f"Ignored event type: {event_type}"}

    # Parse payload
    try:
        import json
        payload = json.loads(body)
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    # Extract push info
    ref = payload.get("ref", "")  # "refs/heads/main"
    if not ref.startswith("refs/heads/"):
        return {"ok": True, "message": f"Ignored non-branch ref: {ref}"}

    branch = ref.replace("refs/heads/", "")
    repo_full = payload.get("repository", {}).get("full_name", "")

    if not repo_full:
        raise HTTPException(400, "Missing repository.full_name in payload")

    # Extract project_id from URL path
    # URL: /api/projects/{project_id}/webhooks/github/receive
    path = str(request.url.path)
    parts = path.split("/")
    project_id = ""
    for i, p in enumerate(parts):
        if p == "projects" and i + 1 < len(parts):
            project_id = parts[i + 1]
            break

    if not project_id:
        raise HTTPException(400, "Could not determine project_id from URL")

    # Find matching webhook config
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM webhook_configs WHERE project_id = ? AND github_repo = ? AND github_branch = ? AND enabled = 1",
        [project_id, repo_full, branch],
    )
    row = await cursor.fetchone()

    if not row:
        # Try wildcard branch match (branch = "*")
        cursor = await d.execute(
            "SELECT * FROM webhook_configs WHERE project_id = ? AND github_repo = ? AND github_branch = '*' AND enabled = 1",
            [project_id, repo_full],
        )
        row = await cursor.fetchone()

    if not row:
        return {"ok": False, "message": f"No webhook configured for {repo_full}:{branch}"}

    webhook = dict(row)

    # Validate HMAC signature
    if not signature or not _verify_github_signature(body, signature, webhook["secret"]):
        raise HTTPException(401, "Invalid webhook signature")

    # Extract commit info
    head_commit = payload.get("head_commit", {})
    commit_sha = head_commit.get("id", "")[:8]
    commit_message = head_commit.get("message", "").split("\n")[0][:200]
    author = head_commit.get("author", {}).get("name", payload.get("pusher", {}).get("name", "unknown"))

    # Record delivery
    delivery_row_id = await _record_delivery(
        webhook["id"], event_type, delivery_id, branch, commit_sha, commit_message, author,
    )

    # Trigger deploy if auto_deploy is on
    if not webhook.get("auto_deploy"):
        await _update_delivery(delivery_row_id, "skipped", "", "auto_deploy is disabled")
        return {"ok": True, "message": "Webhook received but auto_deploy is disabled", "delivery_id": delivery_id}

    # Call the ship pipeline
    result = await _trigger_ship(
        project_id=webhook["project_id"],
        workspace_name=webhook["workspace_name"],
        branch=branch,
        instance_id=webhook.get("instance_id", ""),
        commit_sha=commit_sha,
        commit_message=commit_message,
    )

    # Update delivery + webhook status
    now = datetime.now(timezone.utc).isoformat()
    if result.get("ok"):
        await _update_delivery(delivery_row_id, "success", str(result), "")
        await db.update("webhook_configs", webhook["id"], {
            "last_triggered": now, "last_status": "success", "last_error": "",
        })
        logger.info("GitHub webhook deploy success: %s:%s → %s/%s",
                     repo_full, branch, webhook["workspace_name"], commit_sha)
    else:
        error = result.get("error", "Deploy failed")
        await _update_delivery(delivery_row_id, "failed", str(result), error)
        await db.update("webhook_configs", webhook["id"], {
            "last_triggered": now, "last_status": "failed", "last_error": error,
        })
        logger.warning("GitHub webhook deploy failed: %s:%s → %s: %s",
                        repo_full, branch, webhook["workspace_name"], error)

    return {
        "ok": result.get("ok", False),
        "delivery_id": delivery_id,
        "workspace": webhook["workspace_name"],
        "branch": branch,
        "commit": commit_sha,
        "deploy": result,
    }


async def _record_delivery(webhook_id, event, delivery_id, branch, sha, message, author) -> int:
    d = await db.get_db()
    cursor = await d.execute(
        "INSERT INTO webhook_deliveries (webhook_id, event, github_delivery_id, branch, commit_sha, commit_message, author, status, received_at) VALUES (?,?,?,?,?,?,?,?,?)",
        [webhook_id, event, delivery_id, branch, sha, message, author, "pending",
         datetime.now(timezone.utc).isoformat()],
    )
    await d.commit()
    return cursor.lastrowid


async def _update_delivery(row_id: int, status: str, deploy_result: str, error: str):
    d = await db.get_db()
    await d.execute(
        "UPDATE webhook_deliveries SET status = ?, deploy_result = ?, error = ?, finished_at = ? WHERE id = ?",
        [status, deploy_result[:5000], error[:1000], datetime.now(timezone.utc).isoformat(), row_id],
    )
    await d.commit()


async def _trigger_ship(project_id: str, workspace_name: str, branch: str,
                         instance_id: str, commit_sha: str, commit_message: str) -> dict:
    """Trigger the ship pipeline internally by importing the storage routes logic."""
    try:
        from nso.engine.storage.routes import (
            ship_workspace, ShipRequest,
        )

        req = ShipRequest(branch=branch, instance_id=instance_id)
        # Call the ship function directly — it expects project_id from dependency injection
        # so we call it with project_id as a string parameter
        result = await ship_workspace(name=workspace_name, req=req, project_id=project_id)
        return {"ok": True, **result}
    except HTTPException as e:
        return {"ok": False, "error": f"HTTP {e.status_code}: {e.detail}"}
    except Exception as e:
        logger.exception("Ship pipeline failed for webhook deploy")
        return {"ok": False, "error": str(e)}
