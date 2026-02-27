from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

class Stage(str, Enum):
    BOOTING = "booting"
    FIREWALL = "firewall"
    PACKAGES = "packages"
    CLONE_REPO = "clone_repo"
    PYTHON_SETUP = "python_setup"
    NGINX_SETUP = "nginx_setup"
    DATA_DIRS = "data_dirs"
    SERVICE_START = "service_start"
    HEALTH_CHECK = "health_check"
    READY = "ready"
    ERROR = "error"


STAGE_ORDER: list[tuple[Stage, int]] = [
    (Stage.BOOTING, 0),
    (Stage.FIREWALL, 5),
    (Stage.PACKAGES, 15),
    (Stage.CLONE_REPO, 35),
    (Stage.PYTHON_SETUP, 55),
    (Stage.NGINX_SETUP, 70),
    (Stage.DATA_DIRS, 80),
    (Stage.SERVICE_START, 90),
    (Stage.HEALTH_CHECK, 95),
    (Stage.READY, 100),
]

STAGE_PROGRESS = {stage: pct for stage, pct in STAGE_ORDER}

class MetricReport(BaseModel):
    instance_id: str
    token: str
    stage: Stage
    progress: int = 0
    message: str = ""
    error: Optional[str] = None


class StageInfo(BaseModel):
    name: str
    status: str = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_s: Optional[float] = None
    message: str = ""


class InstanceMetrics(BaseModel):
    instance_id: str
    current_stage: str = "booting"
    progress: int = 0
    stages: list[StageInfo] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_s: float = 0
    estimated_remaining_s: float = 0
    error: Optional[str] = None

class HealthResponse(BaseModel):
    service: str = "nso-agent"
    status: str = "ok"
    version: str = "0.2.0"
    tracked_instances: int = 0
    features: list[str] = Field(default_factory=lambda: [
        "auth",
        "metrics",
        "files",
        "exec",
        "services",
        "deploy",
        "snapshots",
        "rollback",
        "self-update",
    ])
