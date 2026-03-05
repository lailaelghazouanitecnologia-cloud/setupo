from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class NodeRole(str, Enum):
    BUILDER = "builder"
    RUNNER = "runner"
    HYBRID = "hybrid"


class NodeStatus(str, Enum):
    ACTIVE = "active"
    DRAINING = "draining"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class BuildStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    BUILDING = "building"
    PUSHING = "pushing"
    DONE = "done"
    FAILED = "failed"


class LoadLevel(str, Enum):
    LOW = "low"          # < 40%
    MEDIUM = "medium"    # 40-70%
    HIGH = "high"        # 70-90%
    CRITICAL = "critical"  # > 90%


# ── Pool Node ──────────────────────────────────────────────

class PoolNode(BaseModel):
    id: str
    instance_id: str
    label: str = ""
    role: NodeRole = NodeRole.HYBRID
    status: NodeStatus = NodeStatus.ACTIVE
    ip: Optional[str] = None
    region: str = "ewr"
    plan: str = "vc2-1c-1gb"
    max_concurrent_builds: int = 2
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    disk_percent: float = 0.0
    active_builds: int = 0
    last_heartbeat: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class RegisterNodeRequest(BaseModel):
    instance_id: str
    label: str = ""
    role: NodeRole = NodeRole.HYBRID
    ip: Optional[str] = None
    region: str = "ewr"
    plan: str = "vc2-1c-1gb"
    max_concurrent_builds: int = 2


class UpdateNodeRequest(BaseModel):
    label: Optional[str] = None
    role: Optional[NodeRole] = None
    status: Optional[NodeStatus] = None
    max_concurrent_builds: Optional[int] = None


# ── Build Queue ────────────────────────────────────────────

class BuildJob(BaseModel):
    id: str
    project_id: str
    workspace: str
    branch: str = "main"
    assigned_node_id: Optional[str] = None
    status: BuildStatus = BuildStatus.QUEUED
    priority: int = 0
    build_command: str = "npm run build"
    logs: str = ""
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    queued_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class SubmitBuildRequest(BaseModel):
    project_id: str
    workspace: str
    branch: str = "main"
    build_command: str = "npm run build"
    priority: int = 0
    deploy_after: bool = True
    target_instance_id: Optional[str] = None


# ── Metrics / Alerts ───────────────────────────────────────

class NodeMetrics(BaseModel):
    node_id: str
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    disk_percent: float = 0.0
    load_avg_1m: float = 0.0
    load_avg_5m: float = 0.0
    load_avg_15m: float = 0.0
    active_builds: int = 0
    uptime_seconds: int = 0
    collected_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ScaleAlert(BaseModel):
    id: str
    node_id: str
    alert_type: str  # "high_cpu", "high_mem", "high_disk", "queue_backlog"
    severity: str = "warning"  # "warning", "critical"
    message: str = ""
    value: float = 0.0
    threshold: float = 0.0
    resolved: bool = False
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved_at: Optional[str] = None


class PoolOverview(BaseModel):
    total_nodes: int = 0
    active_nodes: int = 0
    builders: int = 0
    runners: int = 0
    avg_cpu: float = 0.0
    avg_mem: float = 0.0
    queued_builds: int = 0
    active_builds: int = 0
    completed_builds_24h: int = 0
    failed_builds_24h: int = 0
    alerts: list[ScaleAlert] = Field(default_factory=list)
    nodes: list[PoolNode] = Field(default_factory=list)
