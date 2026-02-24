"""Setupo Models - All Pydantic models for the platform."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────

class InstanceType(str, Enum):
    SETUP = "setup"        # VPS + domain + SSL + nginx — ready for deploy
    DEV = "dev"            # Full dev environment, tooling
    GPU = "gpu"            # GPU instance (Runpod)
    CUSTOM = "custom"      # User-defined specs


class InstanceState(str, Enum):
    CREATING = "creating"
    PROVISIONING = "provisioning"
    READY = "ready"
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DESTROYING = "destroying"


class Provider(str, Enum):
    VULTR = "vultr"
    RUNPOD = "runpod"


# ── Project ──────────────────────────────────────────────────────

class Project(BaseModel):
    id: str                                         # proj_xxxx
    name: str
    api_key_hash: str                               # SHA256 of sk_live_xxxx
    owner: str = ""                                 # email or agent id
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreateProjectRequest(BaseModel):
    name: str
    owner: str = ""


class CreateProjectResponse(BaseModel):
    project: Project
    api_key: str                                    # Only returned once


# ── Instance ─────────────────────────────────────────────────────

class Instance(BaseModel):
    id: str                                         # inst_xxxx
    project_id: str
    type: InstanceType = InstanceType.SETUP
    provider: Provider = Provider.VULTR
    provider_id: str = ""                           # Vultr VPS ID / Runpod Pod ID
    label: str = ""
    region: str = "ewr"                             # Vultr region slug
    plan: str = "vc2-1c-1gb"                        # Vultr plan slug
    os_id: int = 2284                               # Ubuntu 24.04
    ip: Optional[str] = None
    domain: Optional[str] = None                    # User's custom domain
    state: InstanceState = InstanceState.CREATING
    ssh_key_id: Optional[str] = None                # Vultr SSH key ID
    workspace: Optional[str] = None                 # Linked workspace name
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ready_at: Optional[datetime] = None


class CreateInstanceRequest(BaseModel):
    type: InstanceType = InstanceType.SETUP
    label: str = ""
    region: str = "ewr"
    plan: str = "vc2-1c-1gb"
    domain: Optional[str] = None                    # User provides their domain
    workspace: Optional[str] = None                 # Auto-deploy from this workspace


class InstanceExecRequest(BaseModel):
    command: str
    timeout: int = 60


class InstanceExecResponse(BaseModel):
    output: str
    exit_code: int


# ── Workspace ────────────────────────────────────────────────────

class Workspace(BaseModel):
    id: str                                         # ws_xxxx
    project_id: str
    name: str
    path: str                                       # /opt/setupo/data/{project_id}/workspaces/{name}
    git_url: Optional[str] = None
    branch: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreateWorkspaceRequest(BaseModel):
    name: str
    git_url: Optional[str] = None
    branch: str = "main"


# ── Domain ───────────────────────────────────────────────────────

class DomainRecord(BaseModel):
    id: str                                         # dom_xxxx
    project_id: str
    instance_id: str
    domain: str                                     # Full domain: app.example.com
    record_type: str = "A"                          # A or CNAME
    value: str = ""                                 # IP address
    cf_zone_id: Optional[str] = None                # If managed via Cloudflare
    cf_record_id: Optional[str] = None
    proxied: bool = False
    managed: bool = False                           # True if we manage DNS via CF
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreateDomainRequest(BaseModel):
    instance_id: str
    domain: str
    cf_api_token: Optional[str] = None              # If user wants auto DNS
    cf_zone_id: Optional[str] = None
    proxied: bool = False


# ── Deploy ───────────────────────────────────────────────────────

class DeployRequest(BaseModel):
    workspace: str
    branch: str = "main"
    command: Optional[str] = None                   # Override start command


class DeployState(str, Enum):
    SYNCING = "syncing"
    INSTALLING = "installing"
    STARTING = "starting"
    LIVE = "live"
    FAILED = "failed"


class DeployStatus(BaseModel):
    instance_id: str
    state: DeployState
    workspace: str
    logs: list[str] = Field(default_factory=list)
    url: Optional[str] = None


# ── Capabilities (agent-friendly) ───────────────────────────────

class Capabilities(BaseModel):
    version: str = "0.1.0"
    instance_types: list[dict[str, Any]] = Field(default_factory=list)
    regions: list[dict[str, str]] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
