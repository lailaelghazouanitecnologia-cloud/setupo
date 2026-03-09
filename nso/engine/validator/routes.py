"""
Validator API routes.

Routes:
  POST   /validate/{workspace}           — Run checks from validate.toml
  POST   /validate/run                   — Run inline checks (no file needed)
  GET    /validate/checks                — List saved check definitions
  POST   /validate/checks                — Save a check definition
  GET    /validate/checks/{name}         — Get check by name
  DELETE /validate/checks/{name}         — Delete check
  POST   /validate/checks/{name}/run     — Execute a single saved check
  GET    /validate/runs                  — List validation run history
  GET    /validate/runs/{run_id}         — Get run with results
"""

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project, require_project_admin, require_user, AuthContext
from nso.config import settings
from . import service

logger = logging.getLogger("nso.routes.validator")
router = APIRouter()


# ── Request models ──

class InlineCheck(BaseModel):
    name: str
    type: str = "http"
    description: str = ""
    config: dict = {}
    metadata: dict = {}


class RunInlineRequest(BaseModel):
    checks: list[InlineCheck]
    context: dict = {}
    persist: bool = False
    metadata: dict = {}


class SaveCheckRequest(BaseModel):
    name: str
    type: str = "http"
    description: str = ""
    config: dict = {}
    metadata: dict = {}
    enabled: bool = True


# ── Run from validate.toml ──

@router.post("/{workspace}")
async def validate_workspace(
    workspace: str,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """
    Run validation checks defined in a workspace's validate.toml.

    Reads validate.toml from the workspace directory, parses checks,
    executes them, and persists the run.
    """
    ws = await db.fetch_one("workspaces", project_id=project_id, name=workspace)
    if not ws:
        raise HTTPException(404, f"Workspace '{workspace}' not found")

    ws_path = ws.get("path", "")
    toml_path = os.path.join(ws_path, "validate.toml")

    if not os.path.isfile(toml_path):
        raise HTTPException(404, f"No validate.toml found in workspace '{workspace}'")

    try:
        with open(toml_path) as f:
            content = f.read()
        validations = service.parse_validate_toml(content, project_id=project_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not validations:
        return {"status": "skipped", "message": "No checks defined in validate.toml"}

    # Build context for template resolution
    context = await _build_context(project_id, workspace, ws)

    run = await service.execute_batch(
        validations,
        project_id=project_id,
        workspace=workspace,
        instance_id=ws.get("instance_id", ""),
        trigger="manual",
        context=context,
        persist=True,
        metadata={"user_id": auth.user_id or ""},
    )

    return run.to_dict()


# ── Run inline checks ──

@router.post("/run")
async def validate_inline(
    req: RunInlineRequest,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Run ad-hoc validation checks without a validate.toml file."""
    if not req.checks:
        raise HTTPException(400, "No checks provided")

    validations = []
    for check in req.checks:
        validations.append(service.Validation(
            name=check.name,
            type=check.type,
            description=check.description,
            config=check.config,
            metadata=check.metadata,
            project_id=project_id,
        ))

    run = await service.execute_batch(
        validations,
        project_id=project_id,
        trigger="api",
        context=req.context,
        persist=req.persist,
        metadata={**req.metadata, "user_id": auth.user_id or ""},
    )

    return run.to_dict()


# ── CRUD for saved check definitions ──

@router.get("/checks")
async def list_checks(project_id: str = Depends(require_project)):
    """List all saved validation check definitions."""
    checks = await service.list_validations(project_id)
    return {"checks": checks}


@router.post("/checks")
async def create_check(
    req: SaveCheckRequest,
    project_id: str = Depends(require_project_admin),
    auth: AuthContext = Depends(require_user),
):
    """Save a validation check definition (upserts by name)."""
    validation = service.Validation(
        name=req.name,
        type=req.type,
        description=req.description,
        config=req.config,
        metadata=req.metadata,
        project_id=project_id,
        enabled=req.enabled,
        created_by=auth.user_id or "",
        persist=True,
    )

    row = await service.save_validation(validation)
    return {"ok": True, "check": row}


@router.get("/checks/{name}")
async def get_check(
    name: str,
    project_id: str = Depends(require_project),
):
    """Get a saved check definition by name."""
    check = await service.get_validation(project_id, name)
    if not check:
        raise HTTPException(404, f"Check '{name}' not found")
    return check


@router.delete("/checks/{name}")
async def delete_check(
    name: str,
    project_id: str = Depends(require_project_admin),
):
    """Delete a saved check definition."""
    deleted = await service.delete_validation(project_id, name)
    if not deleted:
        raise HTTPException(404, f"Check '{name}' not found")
    return {"ok": True, "deleted": name}


@router.post("/checks/{name}/run")
async def run_saved_check(
    name: str,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Execute a single saved check by name."""
    check_data = await service.get_validation(project_id, name)
    if not check_data:
        raise HTTPException(404, f"Check '{name}' not found")

    validation = service.Validation.from_dict(check_data)
    context = await _build_context(project_id)

    result = await service.execute_validation(validation, context=context)

    return result.to_dict()


# ── Run history ──

@router.get("/runs")
async def list_runs(
    project_id: str = Depends(require_project),
    limit: int = 20,
):
    """List recent validation runs."""
    runs = await service.list_runs(project_id, limit=limit)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    project_id: str = Depends(require_project),
):
    """Get a validation run with all results."""
    run = await service.get_run(run_id)
    if not run or run.get("project_id") != project_id:
        raise HTTPException(404, "Run not found")
    return run


# ── Helpers ──

async def _build_context(
    project_id: str,
    workspace: str = "",
    ws: dict | None = None,
) -> dict[str, Any]:
    """Build template variable context for config resolution."""
    context: dict[str, Any] = {"project_id": project_id}

    if workspace:
        context["workspace"] = workspace

    # Get instance IP for domain resolution
    if ws and ws.get("instance_id"):
        inst = await db.fetch_one("instances", id=ws["instance_id"])
        if inst:
            context["ip"] = inst.get("ip", "")
            context["instance_id"] = inst.get("id", "")

    # Get domain
    if workspace:
        domains = await db.fetch_all("domains", project_id=project_id)
        for dom in domains:
            domain_name = dom.get("domain", "")
            if workspace in domain_name:
                context["domain"] = domain_name
                break

    # Get project owner subdomain
    project = await db.fetch_one("projects", id=project_id)
    if project and project.get("owner"):
        owner = await db.fetch_one("users", id=project["owner"])
        if owner and owner.get("subdomain"):
            context["subdomain"] = owner["subdomain"]
            if workspace and not context.get("domain"):
                context["domain"] = f"{workspace}.{owner['subdomain']}.{settings.NSO_BASE_DOMAIN}"

    return context
