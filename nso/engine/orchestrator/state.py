"""
Desired State Model — the declarative spec for infrastructure.

Users declare WHAT they want. The reconciler converges reality to match.

Three resource types:
  InstanceSpec   — "I want a VPS with this plan, running this workspace"
  WorkspaceSpec  — "I want this workspace at this version on these instances"
  SystemSpec     — "I want N instances of this type with auto-scaling rules"

Each resource has:
  spec            — what the user wants (changed by user)
  status          — what actually exists (changed by reconciler)
  spec_generation — incremented on each spec change
  conditions      — structured status signals (Ready, Healthy, Deployed, etc.)
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from nso.shared import db

logger = logging.getLogger("nso.orchestrator.state")


# ── Conditions ──

class ConditionStatus(str, Enum):
    TRUE = "True"
    FALSE = "False"
    UNKNOWN = "Unknown"


class Condition(BaseModel):
    """A single status condition (Kubernetes-style)."""
    type: str                                           # e.g. "Ready", "Provisioned", "Deployed"
    status: ConditionStatus = ConditionStatus.UNKNOWN
    reason: str = ""                                    # machine-readable reason code
    message: str = ""                                   # human-readable message
    last_transition: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    observed_generation: int = 0                        # spec_generation when this was set


def set_condition(conditions: list[Condition], type_: str, status: ConditionStatus,
                  reason: str, message: str, generation: int = 0) -> list[Condition]:
    """Set or update a condition in a conditions list. Returns the updated list."""
    now = datetime.now(timezone.utc).isoformat()
    for c in conditions:
        if c.type == type_:
            if c.status != status:
                c.last_transition = now
            c.status = status
            c.reason = reason
            c.message = message
            c.observed_generation = generation
            return conditions

    conditions.append(Condition(
        type=type_,
        status=status,
        reason=reason,
        message=message,
        last_transition=now,
        observed_generation=generation,
    ))
    return conditions


def get_condition(conditions: list[Condition], type_: str) -> Condition | None:
    """Get a condition by type."""
    for c in conditions:
        if c.type == type_:
            return c
    return None


# ── Instance Spec ──

class InstancePhase(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    INSTALLING = "installing"
    READY = "ready"
    RUNNING = "running"
    UPDATING = "updating"
    ERROR = "error"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


class InstanceSpec(BaseModel):
    """What a user WANTS an instance to look like."""
    provider: str = "vultr"
    plan: str = "vc2-1c-1gb"
    region: str = "ewr"
    os_id: int = 2136
    workspace: str = ""                     # workspace to deploy
    workspace_branch: str = "main"
    domain: str = ""
    auto_ssl: bool = True
    processes: list[dict] = Field(default_factory=list)  # process specs for supervisor
    metadata: dict[str, Any] = Field(default_factory=dict)


class InstanceStatus(BaseModel):
    """What an instance ACTUALLY looks like (set by reconciler)."""
    phase: InstancePhase = InstancePhase.PENDING
    ip: str = ""
    provider_id: str = ""
    agent_version: str = ""
    deployed_version: str = ""
    deployed_workspace: str = ""
    converged: bool = False
    error: str = ""
    conditions: list[Condition] = Field(default_factory=list)
    last_reconciled: str = ""
    system_metrics: dict[str, Any] = Field(default_factory=dict)
    process_states: dict[str, Any] = Field(default_factory=dict)


class InstanceResource(BaseModel):
    """Full instance resource = metadata + spec + status."""
    id: str
    project_id: str
    name: str = ""
    spec: InstanceSpec = Field(default_factory=InstanceSpec)
    status: InstanceStatus = Field(default_factory=InstanceStatus)
    spec_generation: int = 0
    status_generation: int = 0
    deletion_requested: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Workspace Spec ──

class WorkspaceDeployStatus(str, Enum):
    PENDING = "pending"
    PACKING = "packing"
    PUSHING = "pushing"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"


class WorkspaceSpec(BaseModel):
    """What a user WANTS a workspace to look like."""
    source_type: str = "local"              # local | git
    git_url: str = ""
    branch: str = "main"
    target_instances: list[str] = Field(default_factory=list)
    deploy_config: dict[str, Any] = Field(default_factory=dict)
    processes: list[dict] = Field(default_factory=list)  # process specs
    auto_deploy: bool = True                # deploy on spec change
    version: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceStatus(BaseModel):
    """What a workspace deployment ACTUALLY looks like."""
    deploy_status: WorkspaceDeployStatus = WorkspaceDeployStatus.PENDING
    last_deployed_version: str = ""
    last_deployed_hash: str = ""
    last_deployed_at: str = ""
    r2_key: str = ""                        # current .zar key in R2
    per_instance: dict[str, dict] = Field(default_factory=dict)  # instance_id → {version, status, error}
    conditions: list[Condition] = Field(default_factory=list)
    error: str = ""


class WorkspaceResource(BaseModel):
    """Full workspace resource = metadata + spec + status."""
    id: str
    project_id: str
    name: str
    spec: WorkspaceSpec = Field(default_factory=WorkspaceSpec)
    status: WorkspaceStatus = Field(default_factory=WorkspaceStatus)
    spec_generation: int = 0
    status_generation: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── System Spec (auto-scaling rules) ──

class ScalingPolicy(BaseModel):
    """User-defined scaling rules for a project."""
    min_instances: int = 1
    max_instances: int = 1
    target_cpu_percent: float = 70.0
    target_mem_percent: float = 80.0
    scale_up_cooldown: int = 300            # seconds between scale-ups
    scale_down_cooldown: int = 600
    scale_up_threshold_duration: int = 60   # how long metric must exceed threshold
    scale_down_threshold_duration: int = 180


class SystemSpec(BaseModel):
    """Project-level infrastructure spec."""
    project_id: str
    default_plan: str = "vc2-1c-1gb"
    default_region: str = "ewr"
    scaling: ScalingPolicy = Field(default_factory=ScalingPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── DB persistence for specs ──

SPEC_MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS instance_specs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT DEFAULT '',
        spec TEXT DEFAULT '{}',
        status TEXT DEFAULT '{}',
        spec_generation INTEGER DEFAULT 0,
        status_generation INTEGER DEFAULT 0,
        deletion_requested INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_instance_specs_project ON instance_specs(project_id)",

    """
    CREATE TABLE IF NOT EXISTS workspace_specs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        spec TEXT DEFAULT '{}',
        status TEXT DEFAULT '{}',
        spec_generation INTEGER DEFAULT 0,
        status_generation INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_workspace_specs_project ON workspace_specs(project_id)",

    """
    CREATE TABLE IF NOT EXISTS system_specs (
        project_id TEXT PRIMARY KEY,
        spec TEXT DEFAULT '{}',
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS reconcile_log (
        id TEXT PRIMARY KEY,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        action TEXT NOT NULL,
        result TEXT DEFAULT 'pending',
        detail TEXT DEFAULT '',
        spec_generation INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reconcile_log_resource ON reconcile_log(resource_type, resource_id)",
]


async def apply_instance_spec(project_id: str, instance_id: str, spec: InstanceSpec, name: str = "") -> InstanceResource:
    """Create or update an instance's desired spec. Increments spec_generation."""
    conn = await db.get_db()

    existing = await db.fetch_one("instance_specs", id=instance_id)

    if existing:
        gen = (existing.get("spec_generation") or 0) + 1
        await db.update("instance_specs", instance_id, {
            "spec": spec.model_dump_json(),
            "spec_generation": gen,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        gen = 1
        await db.insert("instance_specs", {
            "id": instance_id,
            "project_id": project_id,
            "name": name,
            "spec": spec.model_dump_json(),
            "status": InstanceStatus().model_dump_json(),
            "spec_generation": gen,
            "status_generation": 0,
        })

    return InstanceResource(
        id=instance_id,
        project_id=project_id,
        name=name,
        spec=spec,
        spec_generation=gen,
    )


async def get_instance_resource(instance_id: str) -> InstanceResource | None:
    """Load an instance resource from DB."""
    row = await db.fetch_one("instance_specs", id=instance_id)
    if not row:
        return None
    return _parse_instance_row(row)


async def list_instance_resources(project_id: str) -> list[InstanceResource]:
    """List all instance resources for a project."""
    rows = await db.fetch_all("instance_specs", project_id=project_id)
    return [_parse_instance_row(r) for r in rows]


async def list_all_instance_resources() -> list[InstanceResource]:
    """List ALL instance resources across all projects (for reconciler)."""
    conn = await db.get_db()
    cursor = await conn.execute("SELECT * FROM instance_specs WHERE deletion_requested = 0")
    rows = await cursor.fetchall()
    return [_parse_instance_row(r) for r in rows]


async def update_instance_status(instance_id: str, status: InstanceStatus, gen: int = 0):
    """Update an instance's observed status (called by reconciler)."""
    update = {
        "status": status.model_dump_json(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if gen > 0:
        update["status_generation"] = gen
    await db.update("instance_specs", instance_id, update)


async def request_instance_deletion(instance_id: str):
    """Mark an instance for deletion (reconciler will destroy it)."""
    await db.update("instance_specs", instance_id, {
        "deletion_requested": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


async def apply_workspace_spec(project_id: str, name: str, spec: WorkspaceSpec) -> WorkspaceResource:
    """Create or update a workspace's desired spec."""
    existing = await db.fetch_one("workspace_specs", project_id=project_id, name=name)

    if existing:
        gen = (existing.get("spec_generation") or 0) + 1
        await db.update("workspace_specs", existing["id"], {
            "spec": spec.model_dump_json(),
            "spec_generation": gen,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        ws_id = existing["id"]
    else:
        gen = 1
        ws_id = f"ws_{secrets.token_hex(8)}"
        await db.insert("workspace_specs", {
            "id": ws_id,
            "project_id": project_id,
            "name": name,
            "spec": spec.model_dump_json(),
            "status": WorkspaceStatus().model_dump_json(),
            "spec_generation": gen,
            "status_generation": 0,
        })

    return WorkspaceResource(
        id=ws_id,
        project_id=project_id,
        name=name,
        spec=spec,
        spec_generation=gen,
    )


async def get_system_spec(project_id: str) -> SystemSpec | None:
    """Get project's system/scaling spec."""
    row = await db.fetch_one("system_specs", project_id=project_id)
    if not row:
        return None
    try:
        data = json.loads(row.get("spec", "{}"))
        data["project_id"] = project_id
        return SystemSpec(**data)
    except Exception:
        return None


async def apply_system_spec(project_id: str, spec: SystemSpec):
    """Set project's system/scaling spec."""
    existing = await db.fetch_one("system_specs", project_id=project_id)
    data = {
        "spec": spec.model_dump_json(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        conn = await db.get_db()
        await conn.execute(
            "UPDATE system_specs SET spec = ?, updated_at = ? WHERE project_id = ?",
            (data["spec"], data["updated_at"], project_id),
        )
        await conn.commit()
    else:
        await db.insert("system_specs", {"project_id": project_id, **data})


async def log_reconcile_action(resource_type: str, resource_id: str, action: str,
                                result: str = "pending", detail: str = "", gen: int = 0):
    """Log a reconciliation action for debugging."""
    await db.insert("reconcile_log", {
        "id": f"rl_{secrets.token_hex(8)}",
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "result": result,
        "detail": detail[:1000],
        "spec_generation": gen,
    })


# ── Internal ──

def _parse_instance_row(row) -> InstanceResource:
    d = dict(row)
    spec = InstanceSpec.model_validate_json(d.get("spec", "{}"))
    status = InstanceStatus.model_validate_json(d.get("status", "{}"))
    return InstanceResource(
        id=d["id"],
        project_id=d.get("project_id", ""),
        name=d.get("name", ""),
        spec=spec,
        status=status,
        spec_generation=d.get("spec_generation", 0),
        status_generation=d.get("status_generation", 0),
        deletion_requested=bool(d.get("deletion_requested", 0)),
        created_at=d.get("created_at", ""),
    )
