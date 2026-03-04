"""
Pydantic models and validation for deploy.toml.

Used by the central server to:
- Validate deploy.toml before shipping
- Resolve ${secret:KEY} references from project secrets
- Convert legacy config.toml to deploy format
"""

import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("nso.deploy_config")


# ── Sub-models ──────────────────────────────────────────────────

class FirewallRule(BaseModel):
    port: int | str = ""
    proto: str = "tcp"
    from_addr: str = Field("", alias="from")
    action: str = "allow"

    model_config = {"populate_by_name": True}


class SystemUser(BaseModel):
    name: str
    shell: str = "/bin/bash"
    home: str = ""
    groups: list[str] = Field(default_factory=list)


class SystemServices(BaseModel):
    enable: list[str] = Field(default_factory=list)
    disable: list[str] = Field(default_factory=list)


class SystemConfig(BaseModel):
    packages: list[str] = Field(default_factory=list)
    locale: str = ""
    firewall: list[FirewallRule] = Field(default_factory=list)
    users: list[SystemUser] = Field(default_factory=list)
    services: SystemServices = Field(default_factory=SystemServices)


class DirEntry(BaseModel):
    path: str
    owner: str = ""
    mode: str = "0755"


class FileEntry(BaseModel):
    path: str
    content: str = ""
    owner: str = ""
    mode: str = "0644"
    template: bool = False


class ScriptEntry(BaseModel):
    name: str = "unnamed"
    command: str = ""
    timeout: int = 60
    user: str = ""
    on_fail: str = "abort"  # abort | warn | ignore


class SetupDirs(BaseModel):
    create: list[DirEntry] = Field(default_factory=list)


class SetupConfig(BaseModel):
    working_dir: str = "/opt/app"
    dirs: SetupDirs = Field(default_factory=SetupDirs)
    files: list[FileEntry] = Field(default_factory=list)
    scripts: list[ScriptEntry] = Field(default_factory=list)


class InstallConfig(BaseModel):
    command: str = ""
    timeout: int = 300


class BuildStep(BaseModel):
    name: str = "unnamed"
    command: str = ""
    timeout: int = 120


class BuildConfig(BaseModel):
    command: str = ""
    timeout: int = 600
    env: dict[str, str] = Field(default_factory=dict)
    steps: list[BuildStep] = Field(default_factory=list)


class ServiceConfig(BaseModel):
    command: str = ""
    port: int | None = None
    user: str = "root"
    restart: str = "on-failure"
    env: dict[str, str] = Field(default_factory=dict)
    working_dir: str = ""
    depends_on: list[str] = Field(default_factory=list)


class NginxProxy(BaseModel):
    target: str = "http://127.0.0.1:3000"
    websocket: bool = False
    read_timeout: str = "60s"
    body_max_size: str = "10m"


class NginxStatic(BaseModel):
    root: str = "/opt/app/dist"
    index: str = "index.html"
    spa: bool = False
    cache: str = ""


class NginxLocation(BaseModel):
    path: str
    alias: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class NginxConfig(BaseModel):
    type: str = "proxy"  # proxy | static | custom
    proxy: NginxProxy = Field(default_factory=NginxProxy)
    static: NginxStatic = Field(default_factory=NginxStatic)
    locations: list[NginxLocation] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)


class DomainConfig(BaseModel):
    name: str
    ssl: bool = True
    primary: bool = False
    type: str = "primary"  # primary | alias


class MigrateConfig(BaseModel):
    command: str = ""
    timeout: int = 120
    on_fail: str = "abort"


class SeedConfig(BaseModel):
    command: str = ""
    timeout: int = 60
    on_fail: str = "warn"
    only_if: str = "always"  # first_deploy | always | never


class DataConfig(BaseModel):
    migrate: MigrateConfig = Field(default_factory=MigrateConfig)
    seed: SeedConfig = Field(default_factory=SeedConfig)
    scripts: list[ScriptEntry] = Field(default_factory=list)


class HealthHttp(BaseModel):
    url: str = "http://localhost:3000/health"
    method: str = "GET"
    status: int = 200
    timeout: int = 10
    retries: int = 5
    interval: int = 3
    body_contains: str = ""


class HealthTcp(BaseModel):
    host: str = "localhost"
    port: int = 3000
    timeout: int = 5
    retries: int = 10
    interval: int = 2


class HealthCommand(BaseModel):
    run: str = ""
    timeout: int = 10
    retries: int = 5
    interval: int = 3


class HealthConfig(BaseModel):
    strategy: str = "none"  # http | tcp | command | none
    http: HealthHttp = Field(default_factory=HealthHttp)
    tcp: HealthTcp = Field(default_factory=HealthTcp)
    command: HealthCommand = Field(default_factory=HealthCommand)


class HookEntry(BaseModel):
    name: str = "unnamed"
    command: str = ""
    timeout: int = 60
    on_fail: str = "ignore"  # abort | warn | ignore | rollback


class HooksConfig(BaseModel):
    pre_deploy: list[HookEntry] = Field(default_factory=list)
    post_deploy: list[HookEntry] = Field(default_factory=list)
    on_rollback: list[HookEntry] = Field(default_factory=list)


class RollbackConfig(BaseModel):
    auto: bool = True
    max_snapshots: int = 5
    keep_data: bool = True


class PackageDep(BaseModel):
    name: str = ""
    branch: str = "main"
    version: str = ""


class PackageConfig(BaseModel):
    version: str = "0.1.0"
    branch: str = "main"
    dependencies: dict[str, PackageDep] = Field(default_factory=dict)


class WorkspaceInfo(BaseModel):
    name: str = ""
    type: str = "custom"
    description: str = ""
    version: str = ""


# ── Root model ──────────────────────────────────────────────────

class DeployConfig(BaseModel):
    """Full deploy.toml schema."""
    workspace: WorkspaceInfo = Field(default_factory=WorkspaceInfo)
    system: SystemConfig = Field(default_factory=SystemConfig)
    setup: SetupConfig = Field(default_factory=SetupConfig)
    install: InstallConfig = Field(default_factory=InstallConfig)
    build: BuildConfig = Field(default_factory=BuildConfig)
    services: dict[str, ServiceConfig] = Field(default_factory=dict)
    nginx: NginxConfig = Field(default_factory=NginxConfig)
    domains: list[DomainConfig] = Field(default_factory=list)
    data: DataConfig = Field(default_factory=DataConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    rollback: RollbackConfig = Field(default_factory=RollbackConfig)
    env: dict[str, str] = Field(default_factory=dict)
    package: PackageConfig = Field(default_factory=PackageConfig)


# ── Helper functions ────────────────────────────────────────────

def find_secret_refs(config_dict: dict) -> list[str]:
    """Find all ${secret:KEY} references in a config dict."""
    refs = set()
    _find_refs_recursive(config_dict, refs)
    return sorted(refs)


def _find_refs_recursive(obj: Any, refs: set):
    if isinstance(obj, str):
        for m in re.finditer(r'\$\{secret:([^}]+)\}', obj):
            refs.add(m.group(1))
    elif isinstance(obj, dict):
        for v in obj.values():
            _find_refs_recursive(v, refs)
    elif isinstance(obj, list):
        for v in obj:
            _find_refs_recursive(v, refs)


def resolve_secret_refs(config_dict: dict, secrets: dict[str, str]) -> dict:
    """Replace ${secret:KEY} references with actual values."""
    return _resolve_recursive(config_dict, secrets)


def _resolve_recursive(obj: Any, secrets: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return re.sub(
            r'\$\{secret:([^}]+)\}',
            lambda m: secrets.get(m.group(1), m.group(0)),
            obj,
        )
    if isinstance(obj, dict):
        return {k: _resolve_recursive(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_recursive(v, secrets) for v in obj]
    return obj


def from_legacy_config(workspace_config) -> dict:
    """Convert a legacy WorkspaceConfig to deploy.toml dict format.

    This allows old config.toml workspaces to use the new pipeline.
    """
    result: dict[str, Any] = {
        "workspace": {
            "name": workspace_config.name,
            "type": workspace_config.type,
            "description": workspace_config.description,
        },
    }

    # Deploy section → services + env
    if workspace_config.deploy:
        d = workspace_config.deploy
        if d.command:
            result["services"] = {
                "web": {
                    "command": d.command,
                    "port": d.port or 3000,
                }
            }
        if d.env:
            result["env"] = dict(d.env)

    # Services → domains
    if workspace_config.services:
        domains = []
        for svc_name, svc in workspace_config.services.items():
            if svc.domain:
                domains.append({
                    "name": svc.domain,
                    "ssl": svc.ssl,
                })
        if domains:
            result["domains"] = domains

    return result
