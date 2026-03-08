from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DeviceStatus:
    PENDING = "pending"
    PROVISIONING = "provisioning"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class RegisterDeviceRequest(BaseModel):
    name: str
    host: str
    ssh_port: int = 22
    ssh_user: str = "root"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateDeviceRequest(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class ActivateDeviceRequest(BaseModel):
    token: str
    fingerprint: str = ""
    os: str = ""
    agent_version: str = ""


class DeviceExecRequest(BaseModel):
    command: str
    timeout: int = 60


class GroupExecRequest(BaseModel):
    command: str
    timeout: int = 60


class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddDevicesToGroupRequest(BaseModel):
    device_ids: list[str]


class GroupDeployRequest(BaseModel):
    workspace: str
    branch: str = "main"
