"""Setupo Models - All Pydantic models for the platform."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────

class WorkspaceType(str, Enum):
    CUSTOM = "custom"      # Empty workspace, user writes code
    GIT = "git"            # Cloned from a git repo
    TEMPLATE = "template"  # Created from a built-in template


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

class WorkspaceGitConfig(BaseModel):
    url: Optional[str] = None
    branch: str = "main"
    auto_pull: bool = False


class WorkspaceDeployConfig(BaseModel):
    instance_id: Optional[str] = None              # Linked instance
    command: Optional[str] = None                  # Start command override
    port: int = 3000
    env: dict[str, str] = Field(default_factory=dict)


class WorkspaceServiceConfig(BaseModel):
    enabled: bool = True
    domain: Optional[str] = None
    ssl: bool = True


class WorkspaceConfig(BaseModel):
    """Represents the config.toml for a workspace."""
    name: str
    type: str = "custom"                           # python | node | static | docker | go | rust
    description: str = ""
    git: WorkspaceGitConfig = Field(default_factory=WorkspaceGitConfig)
    deploy: WorkspaceDeployConfig = Field(default_factory=WorkspaceDeployConfig)
    services: dict[str, WorkspaceServiceConfig] = Field(default_factory=dict)


class Workspace(BaseModel):
    id: str                                         # ws_xxxx
    project_id: str
    name: str
    path: str                                       # workspaces/{name}
    ws_type: WorkspaceType = WorkspaceType.CUSTOM
    stack: str = ""                                 # python | node | static | etc.
    description: str = ""
    instance_id: Optional[str] = None               # Linked instance
    git_url: Optional[str] = None
    branch: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateWorkspaceRequest(BaseModel):
    name: str
    ws_type: WorkspaceType = WorkspaceType.CUSTOM
    stack: str = ""                                 # python | node | static
    description: str = ""
    git_url: Optional[str] = None
    branch: str = "main"
    instance_id: Optional[str] = None               # Link to instance on creation


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


# ── Zar Packages ────────────────────────────────────────────────

class ZarDependency(BaseModel):
    """A dependency on another workspace's .zar package."""
    name: str                                       # Workspace name
    branch: str = "main"
    version: str = ""                               # Semver constraint, e.g. ">=1.0.0"
    path: str = ""                                  # Where to extract inside the workspace


class ZarManifest(BaseModel):
    """Metadata inside a .zar package (.zar-manifest.json)."""
    name: str
    version: str = "0.1.0"
    branch: str = "main"
    hash: str = ""                                  # sha256 of the .zar file
    stack: str = ""                                 # node | python | static | etc.
    created_at: str = ""
    dependencies: list[ZarDependency] = Field(default_factory=list)
    parent: str = ""                                # Hash of previous version
    project_id: str = ""
    description: str = ""


class PackageConfig(BaseModel):
    """[package] section in config.toml."""
    version: str = "0.1.0"
    branch: str = "main"
    dependencies: dict[str, ZarDependency] = Field(default_factory=dict)


class R2Config(BaseModel):
    """[package.r2] section in config.toml."""
    bucket: str = "nso"
    endpoint: str = ""                              # R2 S3-compatible endpoint
    access_key_id: str = ""
    secret_access_key: str = ""
    public_url: str = ""                            # Optional public bucket URL


class ZarUploadResult(BaseModel):
    name: str
    version: str
    branch: str
    hash: str
    r2_key: str
    size: int


class ZarDeployRequest(BaseModel):
    """What the API sends to the agent to deploy a .zar."""
    r2_key: str                                     # Key in R2 bucket
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    target_dir: str = "/opt/app"                    # Where to extract
    restart_service: str = "setupo-app"             # Service to restart after
    manifest: ZarManifest | None = None


class ZarDeployStatus(BaseModel):
    """Current deployment state on the agent."""
    current_version: str = ""
    current_hash: str = ""
    workspace: str = ""
    branch: str = ""
    deployed_at: str = ""
    manifest: ZarManifest | None = None
    snapshots: list[str] = Field(default_factory=list)  # Available rollback versions


# ── Capabilities (agent-friendly) ───────────────────────────────

class Capabilities(BaseModel):
    version: str = "0.1.0"
    instance_types: list[dict[str, Any]] = Field(default_factory=list)
    regions: list[dict[str, str]] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
