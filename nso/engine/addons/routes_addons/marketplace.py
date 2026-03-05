"""NSO Addons — Marketplace app endpoints: uptime monitor, SSL manager, scheduled tasks."""

import logging
import secrets as token_gen
import ssl
import socket
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project

logger = logging.getLogger("nso.addons.marketplace")
router = APIRouter()

_TIMEOUT = 10.0


async def _require_marketplace_app(project_id: str, app_id: str):
    """Check that a marketplace app is installed and enabled."""
    addon = await db.fetch_one("addons", project_id=project_id, addon_id=app_id, addon_type="marketplace")
    if not addon or not addon.get("enabled"):
        raise HTTPException(403, f"Marketplace app '{app_id}' is not installed or is disabled")
    return addon


@router.get("/{app_id}/status")
async def marketplace_app_status(app_id: str, project_id: str = Depends(require_project)):
    """Get the status of an installed marketplace app."""
    addon = await _require_marketplace_app(project_id, app_id)

    # Enrich with app-specific stats
    stats = {}
    if app_id == "uptime-monitor":
        targets = await db.fetch_all("uptime_targets", project_id=project_id)
        stats["targets"] = len(targets)
        stats["active"] = sum(1 for t in targets if t.get("enabled"))
    elif app_id == "ssl-manager":
        certs = await db.fetch_all("ssl_certificates", project_id=project_id)
        stats["certificates"] = len(certs)
        stats["expiring_soon"] = sum(1 for c in certs if 0 <= c.get("days_remaining", -1) <= 14)
    elif app_id == "scheduled-tasks":
        tasks = await db.fetch_all("scheduled_tasks", project_id=project_id)
        stats["tasks"] = len(tasks)
        stats["active"] = sum(1 for t in tasks if t.get("enabled"))

    return {
        "app_id": app_id,
        "name": addon["name"],
        "version": addon["version"],
        "enabled": addon["enabled"],
        "config": addon.get("config", {}),
        "installed_at": addon.get("installed_at"),
        "stats": stats,
    }


# ═══════════════════════════════════════════════════════════════
#  UPTIME MONITOR
# ═══════════════════════════════════════════════════════════════

class UptimeTargetRequest(BaseModel):
    url: str
    label: str = ""
    interval_seconds: int = 60
    timeout_seconds: int = 10
    expected_status: int = 200
    notify_slack: bool = False
    notify_email: bool = False


@router.get("/uptime-monitor/targets")
async def list_uptime_targets(project_id: str = Depends(require_project)):
    """List all uptime monitoring targets."""
    await _require_marketplace_app(project_id, "uptime-monitor")
    targets = await db.fetch_all("uptime_targets", project_id=project_id)
    return {"targets": targets, "count": len(targets)}


@router.post("/uptime-monitor/targets")
async def create_uptime_target(req: UptimeTargetRequest, project_id: str = Depends(require_project)):
    """Add a URL to monitor for uptime."""
    await _require_marketplace_app(project_id, "uptime-monitor")
    if not req.url.startswith("http"):
        raise HTTPException(400, "URL must start with http:// or https://")

    target_id = f"upt_{token_gen.token_hex(8)}"
    data = {
        "id": target_id,
        "project_id": project_id,
        "url": req.url,
        "label": req.label or req.url,
        "interval_seconds": max(30, req.interval_seconds),
        "timeout_seconds": min(30, req.timeout_seconds),
        "expected_status": req.expected_status,
        "enabled": True,
        "notify_slack": req.notify_slack,
        "notify_email": req.notify_email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("uptime_targets", data)
    return {"ok": True, "target": data}


@router.delete("/uptime-monitor/targets/{target_id}")
async def delete_uptime_target(target_id: str, project_id: str = Depends(require_project)):
    """Remove an uptime target and its history."""
    await _require_marketplace_app(project_id, "uptime-monitor")
    target = await db.fetch_one("uptime_targets", id=target_id)
    if not target or target["project_id"] != project_id:
        raise HTTPException(404, "Target not found")
    # Delete results first
    d = await db.get_db()
    await d.execute("DELETE FROM uptime_results WHERE target_id = ?", [target_id])
    await d.commit()
    await db.delete("uptime_targets", target_id)
    return {"ok": True}


@router.post("/uptime-monitor/targets/{target_id}/check")
async def check_uptime_target(target_id: str, project_id: str = Depends(require_project)):
    """Run an immediate health check on a target."""
    await _require_marketplace_app(project_id, "uptime-monitor")
    target = await db.fetch_one("uptime_targets", id=target_id)
    if not target or target["project_id"] != project_id:
        raise HTTPException(404, "Target not found")

    result = await _do_uptime_check(target)
    return {"ok": True, "result": result}


async def _do_uptime_check(target: dict) -> dict:
    """Perform actual HTTP health check and record the result."""
    url = target["url"]
    expected = target.get("expected_status", 200)
    timeout = target.get("timeout_seconds", 10)

    start = datetime.now(timezone.utc)
    status_code = 0
    is_up = False
    error_msg = ""

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            resp = await c.get(url)
        status_code = resp.status_code
        is_up = status_code == expected
    except httpx.TimeoutException:
        error_msg = "Timeout"
    except httpx.ConnectError as e:
        error_msg = f"Connection failed: {e}"
    except Exception as e:
        error_msg = str(e)

    elapsed = datetime.now(timezone.utc) - start
    response_ms = int(elapsed.total_seconds() * 1000)

    result = {
        "target_id": target["id"],
        "status_code": status_code,
        "response_ms": response_ms,
        "is_up": is_up,
        "error": error_msg,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    # Persist
    d = await db.get_db()
    await d.execute(
        "INSERT INTO uptime_results (target_id, status_code, response_ms, is_up, error, checked_at) VALUES (?,?,?,?,?,?)",
        [result["target_id"], result["status_code"], result["response_ms"],
         int(result["is_up"]), result["error"], result["checked_at"]],
    )
    await d.commit()

    return result


@router.get("/uptime-monitor/targets/{target_id}/history")
async def uptime_history(
    target_id: str,
    limit: int = Query(100, ge=1, le=1000),
    project_id: str = Depends(require_project),
):
    """Get check history for a target."""
    await _require_marketplace_app(project_id, "uptime-monitor")
    target = await db.fetch_one("uptime_targets", id=target_id)
    if not target or target["project_id"] != project_id:
        raise HTTPException(404, "Target not found")

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM uptime_results WHERE target_id = ? ORDER BY id DESC LIMIT ?",
        [target_id, limit],
    )
    rows = await cursor.fetchall()
    checks = [dict(r) for r in rows]

    # Calculate uptime percentage
    total = len(checks)
    up_count = sum(1 for c in checks if c.get("is_up"))
    avg_ms = int(sum(c.get("response_ms", 0) for c in checks) / total) if total else 0
    uptime_pct = round((up_count / total) * 100, 2) if total else 0

    return {
        "target_id": target_id,
        "checks": checks,
        "total": total,
        "uptime_pct": uptime_pct,
        "avg_response_ms": avg_ms,
    }


@router.get("/uptime-monitor/summary")
async def uptime_summary(project_id: str = Depends(require_project)):
    """Get uptime summary for all targets in the project."""
    await _require_marketplace_app(project_id, "uptime-monitor")
    targets = await db.fetch_all("uptime_targets", project_id=project_id)

    summary = []
    d = await db.get_db()
    for t in targets:
        cursor = await d.execute(
            "SELECT * FROM uptime_results WHERE target_id = ? ORDER BY id DESC LIMIT 100",
            [t["id"]],
        )
        checks = [dict(r) for r in await cursor.fetchall()]
        total = len(checks)
        up_count = sum(1 for c in checks if c.get("is_up"))
        last_check = checks[0] if checks else None
        summary.append({
            "target_id": t["id"],
            "url": t["url"],
            "label": t.get("label", t["url"]),
            "enabled": t.get("enabled", True),
            "uptime_pct": round((up_count / total) * 100, 2) if total else 0,
            "last_status": last_check.get("status_code") if last_check else None,
            "last_response_ms": last_check.get("response_ms") if last_check else None,
            "is_up": last_check.get("is_up", False) if last_check else None,
            "total_checks": total,
        })

    return {"targets": summary, "count": len(summary)}


# ═══════════════════════════════════════════════════════════════
#  SSL MANAGER
# ═══════════════════════════════════════════════════════════════

class SSLDomainRequest(BaseModel):
    domain: str
    auto_renew: bool = True


@router.get("/ssl-manager/certificates")
async def list_ssl_certificates(project_id: str = Depends(require_project)):
    """List all tracked SSL certificates."""
    await _require_marketplace_app(project_id, "ssl-manager")
    certs = await db.fetch_all("ssl_certificates", project_id=project_id)
    return {"certificates": certs, "count": len(certs)}


@router.post("/ssl-manager/certificates")
async def add_ssl_domain(req: SSLDomainRequest, project_id: str = Depends(require_project)):
    """Add a domain to track SSL certificate status."""
    await _require_marketplace_app(project_id, "ssl-manager")

    existing = await db.fetch_one("ssl_certificates", project_id=project_id, domain=req.domain)
    if existing:
        raise HTTPException(409, f"Domain '{req.domain}' already tracked")

    cert_id = f"ssl_{token_gen.token_hex(8)}"
    data = {
        "id": cert_id,
        "project_id": project_id,
        "domain": req.domain,
        "auto_renew": req.auto_renew,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.insert("ssl_certificates", data)

    # Immediately check the certificate
    cert_info = await _check_ssl_cert(req.domain)
    updates = {
        "issuer": cert_info.get("issuer", ""),
        "valid_from": cert_info.get("valid_from", ""),
        "valid_to": cert_info.get("valid_to", ""),
        "days_remaining": cert_info.get("days_remaining", -1),
        "status": cert_info.get("status", "unknown"),
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    await db.update("ssl_certificates", cert_id, updates)
    data.update(updates)

    return {"ok": True, "certificate": data}


@router.delete("/ssl-manager/certificates/{cert_id}")
async def remove_ssl_domain(cert_id: str, project_id: str = Depends(require_project)):
    """Stop tracking an SSL certificate."""
    await _require_marketplace_app(project_id, "ssl-manager")
    cert = await db.fetch_one("ssl_certificates", id=cert_id)
    if not cert or cert["project_id"] != project_id:
        raise HTTPException(404, "Certificate not found")
    await db.delete("ssl_certificates", cert_id)
    return {"ok": True}


@router.post("/ssl-manager/certificates/{cert_id}/check")
async def check_ssl_certificate(cert_id: str, project_id: str = Depends(require_project)):
    """Re-check an SSL certificate right now."""
    await _require_marketplace_app(project_id, "ssl-manager")
    cert = await db.fetch_one("ssl_certificates", id=cert_id)
    if not cert or cert["project_id"] != project_id:
        raise HTTPException(404, "Certificate not found")

    info = await _check_ssl_cert(cert["domain"])
    updates = {
        "issuer": info.get("issuer", ""),
        "valid_from": info.get("valid_from", ""),
        "valid_to": info.get("valid_to", ""),
        "days_remaining": info.get("days_remaining", -1),
        "status": info.get("status", "unknown"),
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    await db.update("ssl_certificates", cert_id, updates)
    return {"ok": True, "certificate": {**cert, **updates}}


async def _check_ssl_cert(domain: str) -> dict:
    """Check SSL certificate for a domain using actual TLS connection."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

        # Parse certificate dates
        not_before = datetime.strptime(cert["notBefore"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_remaining = (not_after - datetime.now(timezone.utc)).days

        # Extract issuer
        issuer_parts = dict(x[0] for x in cert.get("issuer", ()))
        issuer = issuer_parts.get("organizationName", issuer_parts.get("commonName", "unknown"))

        status = "valid"
        if days_remaining <= 0:
            status = "expired"
        elif days_remaining <= 7:
            status = "critical"
        elif days_remaining <= 14:
            status = "warning"

        return {
            "issuer": issuer,
            "valid_from": not_before.isoformat(),
            "valid_to": not_after.isoformat(),
            "days_remaining": days_remaining,
            "status": status,
            "subject": dict(x[0] for x in cert.get("subject", ())).get("commonName", domain),
            "san": [x[1] for x in cert.get("subjectAltName", ())],
        }
    except ssl.SSLCertVerificationError as e:
        return {"status": "invalid", "days_remaining": -1, "error": str(e)}
    except socket.timeout:
        return {"status": "timeout", "days_remaining": -1, "error": "Connection timed out"}
    except OSError as e:
        return {"status": "unreachable", "days_remaining": -1, "error": str(e)}


@router.post("/ssl-manager/check-all")
async def check_all_ssl(project_id: str = Depends(require_project)):
    """Re-check all tracked SSL certificates."""
    await _require_marketplace_app(project_id, "ssl-manager")
    certs = await db.fetch_all("ssl_certificates", project_id=project_id)
    results = []
    now = datetime.now(timezone.utc).isoformat()
    for cert in certs:
        info = await _check_ssl_cert(cert["domain"])
        updates = {
            "issuer": info.get("issuer", ""),
            "valid_from": info.get("valid_from", ""),
            "valid_to": info.get("valid_to", ""),
            "days_remaining": info.get("days_remaining", -1),
            "status": info.get("status", "unknown"),
            "last_checked": now,
        }
        await db.update("ssl_certificates", cert["id"], updates)
        results.append({"domain": cert["domain"], **updates})
    return {"ok": True, "results": results, "count": len(results)}


@router.get("/ssl-manager/summary")
async def ssl_summary(project_id: str = Depends(require_project)):
    """Get SSL health summary for the project."""
    await _require_marketplace_app(project_id, "ssl-manager")
    certs = await db.fetch_all("ssl_certificates", project_id=project_id)

    valid = sum(1 for c in certs if c.get("status") == "valid")
    warning = sum(1 for c in certs if c.get("status") == "warning")
    critical = sum(1 for c in certs if c.get("status") == "critical")
    expired = sum(1 for c in certs if c.get("status") == "expired")
    invalid = sum(1 for c in certs if c.get("status") in ("invalid", "unreachable", "timeout"))

    return {
        "total": len(certs),
        "valid": valid,
        "warning": warning,
        "critical": critical,
        "expired": expired,
        "invalid": invalid,
        "certificates": [{
            "domain": c["domain"],
            "status": c.get("status", "unknown"),
            "days_remaining": c.get("days_remaining", -1),
            "issuer": c.get("issuer", ""),
        } for c in certs],
    }


# ═══════════════════════════════════════════════════════════════
#  SCHEDULED TASKS (Cron Jobs)
# ═══════════════════════════════════════════════════════════════

class CreateTaskRequest(BaseModel):
    instance_id: str
    name: str
    command: str
    schedule: str  # cron expression: "*/5 * * * *"
    timezone: str = "UTC"
    max_retries: int = 0
    timeout_seconds: int = 300


class UpdateTaskRequest(BaseModel):
    enabled: Optional[bool] = None
    command: Optional[str] = None
    schedule: Optional[str] = None
    timezone: Optional[str] = None
    max_retries: Optional[int] = None
    timeout_seconds: Optional[int] = None


@router.get("/scheduled-tasks/tasks")
async def list_scheduled_tasks(project_id: str = Depends(require_project)):
    """List all scheduled tasks for the project."""
    await _require_marketplace_app(project_id, "scheduled-tasks")
    tasks = await db.fetch_all("scheduled_tasks", project_id=project_id)
    return {"tasks": tasks, "count": len(tasks)}


@router.post("/scheduled-tasks/tasks")
async def create_scheduled_task(req: CreateTaskRequest, project_id: str = Depends(require_project)):
    """Create a new scheduled task."""
    await _require_marketplace_app(project_id, "scheduled-tasks")

    # Verify instance belongs to project
    inst = await db.fetch_one("instances", id=req.instance_id)
    if not inst or inst["project_id"] != project_id:
        raise HTTPException(404, "Instance not found in this project")

    # Basic cron expression validation (5 fields)
    parts = req.schedule.strip().split()
    if len(parts) != 5:
        raise HTTPException(400, "Invalid cron expression — must have 5 fields (min hour dom mon dow)")

    task_id = f"task_{token_gen.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": task_id,
        "project_id": project_id,
        "instance_id": req.instance_id,
        "name": req.name,
        "command": req.command,
        "schedule": req.schedule,
        "timezone": req.timezone,
        "enabled": True,
        "max_retries": req.max_retries,
        "timeout_seconds": min(3600, req.timeout_seconds),
        "created_at": now,
    }
    await db.insert("scheduled_tasks", data)
    return {"ok": True, "task": data}


@router.patch("/scheduled-tasks/tasks/{task_id}")
async def update_scheduled_task(task_id: str, req: UpdateTaskRequest, project_id: str = Depends(require_project)):
    """Update a scheduled task."""
    await _require_marketplace_app(project_id, "scheduled-tasks")
    task = await db.fetch_one("scheduled_tasks", id=task_id)
    if not task or task["project_id"] != project_id:
        raise HTTPException(404, "Task not found")

    updates = {}
    if req.enabled is not None:
        updates["enabled"] = req.enabled
    if req.command is not None:
        updates["command"] = req.command
    if req.schedule is not None:
        parts = req.schedule.strip().split()
        if len(parts) != 5:
            raise HTTPException(400, "Invalid cron expression")
        updates["schedule"] = req.schedule
    if req.timezone is not None:
        updates["timezone"] = req.timezone
    if req.max_retries is not None:
        updates["max_retries"] = req.max_retries
    if req.timeout_seconds is not None:
        updates["timeout_seconds"] = min(3600, req.timeout_seconds)

    if updates:
        await db.update("scheduled_tasks", task_id, updates)
    return {"ok": True, "updated": list(updates.keys())}


@router.delete("/scheduled-tasks/tasks/{task_id}")
async def delete_scheduled_task(task_id: str, project_id: str = Depends(require_project)):
    """Delete a scheduled task and its execution history."""
    await _require_marketplace_app(project_id, "scheduled-tasks")
    task = await db.fetch_one("scheduled_tasks", id=task_id)
    if not task or task["project_id"] != project_id:
        raise HTTPException(404, "Task not found")

    d = await db.get_db()
    await d.execute("DELETE FROM task_executions WHERE task_id = ?", [task_id])
    await d.commit()
    await db.delete("scheduled_tasks", task_id)
    return {"ok": True}


@router.post("/scheduled-tasks/tasks/{task_id}/run")
async def run_task_now(task_id: str, project_id: str = Depends(require_project)):
    """Execute a scheduled task immediately via the agent."""
    await _require_marketplace_app(project_id, "scheduled-tasks")
    task = await db.fetch_one("scheduled_tasks", id=task_id)
    if not task or task["project_id"] != project_id:
        raise HTTPException(404, "Task not found")

    inst = await db.fetch_one("instances", id=task["instance_id"])
    if not inst or not inst.get("ip"):
        raise HTTPException(400, "Instance not available")

    # Execute via agent
    result = await _exec_on_agent(inst["ip"], task["command"], task.get("timeout_seconds", 300))

    # Record execution
    now = datetime.now(timezone.utc)
    d = await db.get_db()
    await d.execute(
        "INSERT INTO task_executions (task_id, status, exit_code, output, error, started_at, finished_at, duration_ms) VALUES (?,?,?,?,?,?,?,?)",
        [task_id, "success" if result["exit_code"] == 0 else "failed",
         result["exit_code"], result.get("stdout", "")[:10000], result.get("stderr", "")[:5000],
         now.isoformat(), datetime.now(timezone.utc).isoformat(), result.get("duration_ms", 0)],
    )
    await d.commit()

    # Update last_run on the task
    await db.update("scheduled_tasks", task_id, {"last_run": now.isoformat()})

    return {"ok": True, "execution": result}


async def _exec_on_agent(ip: str, command: str, timeout: int) -> dict:
    """Execute a command on an instance via the agent API."""
    from nso.config import settings
    import os

    agent_password = os.environ.get("AGENT_ADMIN_PASSWORD", "")

    # Get agent JWT
    async with httpx.AsyncClient(timeout=10) as c:
        auth_resp = await c.post(f"http://{ip}:8081/auth/login",
                                  json={"password": agent_password})
        if auth_resp.status_code != 200:
            return {"exit_code": -1, "stderr": "Failed to authenticate with agent", "stdout": "", "duration_ms": 0}
        agent_token = auth_resp.json().get("token", "")

    start = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=timeout) as c:
        resp = await c.post(f"http://{ip}:8081/exec/",
                            json={"command": command},
                            headers={"Authorization": f"Bearer {agent_token}"})
    elapsed = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    if resp.status_code != 200:
        return {"exit_code": -1, "stderr": f"Agent error ({resp.status_code})", "stdout": "", "duration_ms": elapsed}

    data = resp.json()
    return {
        "exit_code": data.get("exit_code", data.get("returncode", -1)),
        "stdout": data.get("stdout", data.get("output", "")),
        "stderr": data.get("stderr", ""),
        "duration_ms": elapsed,
    }


@router.get("/scheduled-tasks/tasks/{task_id}/executions")
async def list_task_executions(
    task_id: str,
    limit: int = Query(50, ge=1, le=500),
    project_id: str = Depends(require_project),
):
    """Get execution history for a scheduled task."""
    await _require_marketplace_app(project_id, "scheduled-tasks")
    task = await db.fetch_one("scheduled_tasks", id=task_id)
    if not task or task["project_id"] != project_id:
        raise HTTPException(404, "Task not found")

    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM task_executions WHERE task_id = ? ORDER BY id DESC LIMIT ?",
        [task_id, limit],
    )
    rows = [dict(r) for r in await cursor.fetchall()]

    success = sum(1 for r in rows if r.get("status") == "success")
    return {
        "task_id": task_id,
        "executions": rows,
        "total": len(rows),
        "success_rate": round((success / len(rows)) * 100, 1) if rows else 0,
    }
