"""MMS Data Models - Pydantic models for capsules, environments, pipelines."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────

class CapsuleState(str, Enum):
    CREATED = "created"
    BUILDING = "building"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class RuntimeType(str, Enum):
    PYTHON = "python"
    NODE = "node"
    RUST = "rust"
    GO = "go"
    SHELL = "shell"
    DOCKER = "docker"
    CUSTOM = "custom"


class IsolationLevel(str, Enum):
    NONE = "none"          # Direct execution (dev only)
    VENV = "venv"          # Python virtualenv
    CONTAINER = "container" # Docker container
    NAMESPACE = "namespace" # Linux namespaces


# ── Capsule ──────────────────────────────────────────────────────

class CapsuleManifest(BaseModel):
    """Defines what a capsule IS - its blueprint."""
    name: str
    version: str = "0.1.0"
    description: str = ""
    runtime: RuntimeType = RuntimeType.PYTHON
    isolation: IsolationLevel = IsolationLevel.CONTAINER
    entrypoint: str = "main.py"
    dependencies: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    inputs: list[PortSpec] = Field(default_factory=list)
    outputs: list[PortSpec] = Field(default_factory=list)
    resources: ResourceSpec = Field(default_factory=lambda: ResourceSpec())
    volumes: list[str] = Field(default_factory=list)


class PortSpec(BaseModel):
    """Defines an input/output port on a capsule."""
    name: str
    type: str = "any"  # any, http, grpc, stream, file
    port: int = 0
    protocol: str = "tcp"


class ResourceSpec(BaseModel):
    """Resource limits for a capsule."""
    cpu: float = 1.0       # CPU cores
    memory_mb: int = 256   # RAM in MB
    disk_mb: int = 512     # Disk in MB
    timeout_s: int = 0     # 0 = no timeout


class Capsule(BaseModel):
    """Runtime instance of a capsule."""
    id: str
    manifest: CapsuleManifest
    state: CapsuleState = CapsuleState.CREATED
    container_id: Optional[str] = None
    pid: Optional[int] = None
    ip: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    error: Optional[str] = None
    logs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Environment ──────────────────────────────────────────────────

class Environment(BaseModel):
    """A managed runtime environment."""
    id: str
    name: str
    runtime: RuntimeType
    version: str = ""              # e.g. "3.12", "20.x"
    path: str = ""                 # Path to env root
    packages: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Pipeline ─────────────────────────────────────────────────────

class PipelineStep(BaseModel):
    """A step in a pipeline."""
    capsule: str              # Capsule name or ID
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class Pipeline(BaseModel):
    """A composition of capsules executed in order."""
    id: str
    name: str
    steps: list[PipelineStep]
    state: str = "pending"   # pending, running, completed, failed
    created_at: datetime = Field(default_factory=datetime.now)
    results: dict[str, Any] = Field(default_factory=dict)


# ── API Request/Response ─────────────────────────────────────────

class CreateCapsuleRequest(BaseModel):
    name: str
    runtime: RuntimeType = RuntimeType.PYTHON
    isolation: IsolationLevel = IsolationLevel.CONTAINER
    entrypoint: str = "main.py"
    code: Optional[str] = None         # Inline code
    git_url: Optional[str] = None      # Clone from git
    dependencies: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    ports: list[int] = Field(default_factory=list)
    resources: ResourceSpec = Field(default_factory=lambda: ResourceSpec())


class ExecRequest(BaseModel):
    capsule_id: str
    command: str
    timeout: int = 60


class PipelineRequest(BaseModel):
    name: str
    steps: list[PipelineStep]


class ProtocolRequest(BaseModel):
    code: str
    target: Optional[str] = None
