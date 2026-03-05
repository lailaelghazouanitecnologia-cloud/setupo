"""
Load balancer models — backends, rules, health checks, routing strategies.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class LBAlgorithm(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_conn"
    WEIGHTED = "weighted"
    IP_HASH = "ip_hash"
    LEAST_LOAD = "least_load"       # Based on CPU/mem from orchestrator


class BackendStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    MAINTENANCE = "maintenance"


class HealthCheckType(str, Enum):
    HTTP = "http"
    TCP = "tcp"


# ── Backend (a target server) ────────────────────────────

class Backend(BaseModel):
    id: str
    pool_id: str                    # Which LB pool this belongs to
    instance_id: str                # Links to instances table
    ip: str
    port: int = 8000
    weight: int = 1                 # For weighted algorithm
    status: BackendStatus = BackendStatus.HEALTHY
    active_connections: int = 0
    total_requests: int = 0
    failed_health_checks: int = 0
    last_health_check: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AddBackendRequest(BaseModel):
    instance_id: str
    port: int = 8000
    weight: int = 1


class UpdateBackendRequest(BaseModel):
    weight: Optional[int] = None
    status: Optional[BackendStatus] = None
    port: Optional[int] = None


# ── LB Pool (a group of backends + routing config) ───────

class LBPool(BaseModel):
    id: str
    name: str
    project_id: Optional[str] = None   # None = global pool
    algorithm: LBAlgorithm = LBAlgorithm.ROUND_ROBIN
    health_check_path: str = "/api/health"
    health_check_interval: int = 30     # seconds
    health_check_timeout: int = 5       # seconds
    max_fails: int = 3                  # Mark unhealthy after N consecutive fails
    sticky_sessions: bool = False
    sticky_cookie: str = "NSO_LB_SID"
    backends: list[Backend] = Field(default_factory=list)
    active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CreatePoolRequest(BaseModel):
    name: str
    project_id: Optional[str] = None
    algorithm: LBAlgorithm = LBAlgorithm.ROUND_ROBIN
    health_check_path: str = "/api/health"
    health_check_interval: int = 30
    health_check_timeout: int = 5
    max_fails: int = 3
    sticky_sessions: bool = False


class UpdatePoolRequest(BaseModel):
    name: Optional[str] = None
    algorithm: Optional[LBAlgorithm] = None
    health_check_path: Optional[str] = None
    health_check_interval: Optional[int] = None
    health_check_timeout: Optional[int] = None
    max_fails: Optional[int] = None
    sticky_sessions: Optional[bool] = None
    active: Optional[bool] = None


# ── Routing Rules ─────────────────────────────────────────

class RouteMatchType(str, Enum):
    PREFIX = "prefix"       # /api/billing/* → pool_billing
    EXACT = "exact"         # /api/health → pool_health
    HOST = "host"           # app.nso.dev → pool_app


class LBRule(BaseModel):
    id: str
    pool_id: str
    match_type: RouteMatchType = RouteMatchType.PREFIX
    match_value: str = "/"
    priority: int = 0           # Higher = checked first
    headers: dict[str, str] = Field(default_factory=dict)  # Extra headers to inject
    active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CreateRuleRequest(BaseModel):
    pool_id: str
    match_type: RouteMatchType = RouteMatchType.PREFIX
    match_value: str = "/"
    priority: int = 0
    headers: dict[str, str] = Field(default_factory=dict)


# ── Overview ──────────────────────────────────────────────

class LBOverview(BaseModel):
    total_pools: int = 0
    active_pools: int = 0
    total_backends: int = 0
    healthy_backends: int = 0
    unhealthy_backends: int = 0
    total_rules: int = 0
    total_requests: int = 0
    pools: list[LBPool] = Field(default_factory=list)
