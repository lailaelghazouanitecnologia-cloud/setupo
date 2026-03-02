from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkspaceType(str, Enum):
    CUSTOM = "custom"
    GIT = "git"
    TEMPLATE = "template"


class InstanceType(str, Enum):
    SETUP = "setup"
    DEV = "dev"
    GPU = "gpu"
    CUSTOM = "custom"


class InstanceState(str, Enum):
    CREATING = "creating"
    INSTALLING = "installing"
    READY = "ready"
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DESTROYING = "destroying"


class Provider(str, Enum):
    VULTR = "vultr"
    RUNPOD = "runpod"


class Project(BaseModel):
    id: str
    name: str
    api_key_hash: str
    owner: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreateProjectRequest(BaseModel):
    name: str
    owner: str = ""


class CreateProjectResponse(BaseModel):
    project: Project
    api_key: str


class Instance(BaseModel):
    id: str
    project_id: str
    type: InstanceType = InstanceType.SETUP
    provider: Provider = Provider.VULTR
    provider_id: str = ""
    label: str = ""
    region: str = "ewr"
    plan: str = "vc2-1c-1gb"
    os_id: int = 2284
    ip: Optional[str] = None
    domain: Optional[str] = None
    state: InstanceState = InstanceState.CREATING
    ssh_key_id: Optional[str] = None
    workspace: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ready_at: Optional[datetime] = None


class CreateInstanceRequest(BaseModel):
    type: InstanceType = InstanceType.SETUP
    label: str = ""
    region: str = "ewr"
    plan: str = "vc2-1c-1gb"
    domain: Optional[str] = None
    workspace: Optional[str] = None
    # Source: what to deploy on the instance
    source_type: Optional[str] = None   # "repository" | "zar" | "folder" | None
    git_url: Optional[str] = None       # for source_type="repository"
    git_branch: str = "main"            # for source_type="repository"
    zar_name: Optional[str] = None      # for source_type="zar"


class InstanceExecRequest(BaseModel):
    command: str
    timeout: int = 60


class InstanceExecResponse(BaseModel):
    output: str
    exit_code: int


class WorkspaceGitConfig(BaseModel):
    url: Optional[str] = None
    branch: str = "main"
    auto_pull: bool = False


class WorkspaceDeployConfig(BaseModel):
    instance_id: Optional[str] = None
    command: Optional[str] = None
    port: int = 3000
    env: dict[str, str] = Field(default_factory=dict)


class WorkspaceServiceConfig(BaseModel):
    enabled: bool = True
    domain: Optional[str] = None
    ssl: bool = True


class WorkspaceConfig(BaseModel):
    name: str
    type: str = "custom"
    description: str = ""
    git: WorkspaceGitConfig = Field(default_factory=WorkspaceGitConfig)
    deploy: WorkspaceDeployConfig = Field(default_factory=WorkspaceDeployConfig)
    services: dict[str, WorkspaceServiceConfig] = Field(default_factory=dict)


class Workspace(BaseModel):
    id: str
    project_id: str
    name: str
    path: str
    ws_type: WorkspaceType = WorkspaceType.CUSTOM
    stack: str = ""
    description: str = ""
    instance_id: Optional[str] = None
    git_url: Optional[str] = None
    branch: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateWorkspaceRequest(BaseModel):
    name: str
    ws_type: WorkspaceType = WorkspaceType.CUSTOM
    stack: str = ""
    description: str = ""
    git_url: Optional[str] = None
    branch: str = "main"
    instance_id: Optional[str] = None


class DomainRecord(BaseModel):
    id: str
    project_id: str
    instance_id: str
    domain: str
    record_type: str = "A"
    value: str = ""
    cf_zone_id: Optional[str] = None
    cf_record_id: Optional[str] = None
    proxied: bool = False
    managed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreateDomainRequest(BaseModel):
    instance_id: str
    domain: str
    cf_api_token: Optional[str] = None
    cf_zone_id: Optional[str] = None
    proxied: bool = False


class DeployRequest(BaseModel):
    workspace: str
    branch: str = "main"
    command: Optional[str] = None


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


class ZarDependency(BaseModel):
    name: str
    branch: str = "main"
    version: str = ""
    path: str = ""


class ZarManifest(BaseModel):
    name: str
    version: str = "0.1.0"
    branch: str = "main"
    hash: str = ""
    stack: str = ""
    created_at: str = ""
    dependencies: list[ZarDependency] = Field(default_factory=list)
    parent: str = ""
    project_id: str = ""
    description: str = ""


class PackageConfig(BaseModel):
    version: str = "0.1.0"
    branch: str = "main"
    dependencies: dict[str, ZarDependency] = Field(default_factory=dict)


class R2Config(BaseModel):
    bucket: str = "nso"
    endpoint: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    public_url: str = ""


class ZarUploadResult(BaseModel):
    name: str
    version: str
    branch: str
    hash: str
    r2_key: str
    size: int


class ZarDeployRequest(BaseModel):
    r2_key: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    target_dir: str = "/opt/app"
    restart_service: str = "nso-app"
    manifest: ZarManifest | None = None


class ZarDeployStatus(BaseModel):
    current_version: str = ""
    current_hash: str = ""
    workspace: str = ""
    branch: str = ""
    deployed_at: str = ""
    manifest: ZarManifest | None = None
    snapshots: list[str] = Field(default_factory=list)


class PluginInstallation(BaseModel):
    id: str
    project_id: str
    plugin_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    category: str = ""
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    installed_at: datetime = Field(default_factory=datetime.utcnow)


class InstallPluginRequest(BaseModel):
    plugin_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class UpdatePluginRequest(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class Capabilities(BaseModel):
    version: str = "0.1.0"
    instance_types: list[dict[str, Any]] = Field(default_factory=list)
    regions: list[dict[str, str]] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
