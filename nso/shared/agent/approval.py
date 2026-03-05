"""
Approval — human-in-the-loop tool approval.

Allows requiring human approval before certain tool calls execute.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


@dataclass
class ApprovalRequest:
    request_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    agent_name: str = ""
    run_id: str = ""
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = ""
    resolved_at: str | None = None
    resolved_by: str | None = None
    denial_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = str(uuid.uuid4())[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "agent_name": self.agent_name,
            "run_id": self.run_id,
            "reason": self.reason,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "denial_reason": self.denial_reason,
        }


@dataclass
class ApprovalResult:
    approved: bool = True
    request: ApprovalRequest | None = None
    message: str = ""


@dataclass
class ApprovalPolicy(ABC):
    name: str = ""

    @abstractmethod
    async def check(self, tool_name: str, arguments: dict, context: dict) -> ApprovalResult:
        ...


@dataclass
class RequireApproval(ApprovalPolicy):
    """
    Require explicit human approval before tool execution.

    Usage:
        policy = RequireApproval(
            tools=["shell_run", "file_write"],
            timeout_seconds=300,
            on_timeout="deny",
        )
    """

    name: str = "require_approval"
    tools: list[str] = field(default_factory=list)
    tool_patterns: list[str] = field(default_factory=list)
    timeout_seconds: float = 300.0
    on_timeout: str = "deny"
    callback: Callable[[ApprovalRequest], Any] | None = None

    _pending: dict[str, asyncio.Event] = field(default_factory=dict)
    _requests: dict[str, ApprovalRequest] = field(default_factory=dict)

    def _matches_tool(self, tool_name: str) -> bool:
        if not self.tools and not self.tool_patterns:
            return True
        if tool_name in self.tools:
            return True
        for pattern in self.tool_patterns:
            if pattern.endswith("*") and tool_name.startswith(pattern[:-1]):
                return True
            if pattern == tool_name:
                return True
        return False

    async def check(self, tool_name: str, arguments: dict, context: dict) -> ApprovalResult:
        if not self._matches_tool(tool_name):
            return ApprovalResult(approved=True)

        request = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            agent_name=context.get("agent_name", ""),
            run_id=context.get("run_id", ""),
            reason=f"Tool '{tool_name}' requires approval",
        )

        event = asyncio.Event()
        self._pending[request.request_id] = event
        self._requests[request.request_id] = request

        if self.callback:
            result = self.callback(request)
            if hasattr(result, "__await__"):
                await result

        try:
            await asyncio.wait_for(event.wait(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            request.status = ApprovalStatus.TIMED_OUT
            auto_approve = self.on_timeout == "approve"
            return ApprovalResult(
                approved=auto_approve,
                request=request,
                message=f"Timed out after {self.timeout_seconds}s",
            )
        finally:
            self._pending.pop(request.request_id, None)

        approved = request.status == ApprovalStatus.APPROVED
        return ApprovalResult(
            approved=approved,
            request=request,
            message=request.denial_reason or "",
        )

    def approve(self, request_id: str, approved_by: str = "human") -> bool:
        request = self._requests.get(request_id)
        if not request or request.status != ApprovalStatus.PENDING:
            return False
        request.status = ApprovalStatus.APPROVED
        request.resolved_at = datetime.now(timezone.utc).isoformat()
        request.resolved_by = approved_by
        event = self._pending.get(request_id)
        if event:
            event.set()
        return True

    def deny(self, request_id: str, reason: str = "", denied_by: str = "human") -> bool:
        request = self._requests.get(request_id)
        if not request or request.status != ApprovalStatus.PENDING:
            return False
        request.status = ApprovalStatus.DENIED
        request.resolved_at = datetime.now(timezone.utc).isoformat()
        request.resolved_by = denied_by
        request.denial_reason = reason
        event = self._pending.get(request_id)
        if event:
            event.set()
        return True

    def get_pending(self) -> list[dict]:
        return [r.to_dict() for r in self._requests.values() if r.status == ApprovalStatus.PENDING]


@dataclass
class AuditOnly(ApprovalPolicy):
    """Audit-only — logs tool calls but doesn't block."""

    name: str = "audit_only"
    tools: list[str] = field(default_factory=list)
    log_callback: Callable[[str, dict, dict], Any] | None = None

    async def check(self, tool_name: str, arguments: dict, context: dict) -> ApprovalResult:
        if self.tools and tool_name not in self.tools:
            return ApprovalResult(approved=True)

        logger.info("AUDIT: %s called with %s", tool_name, arguments)

        if self.log_callback:
            result = self.log_callback(tool_name, arguments, context)
            if hasattr(result, "__await__"):
                await result

        return ApprovalResult(approved=True, message=f"Audited: {tool_name}")


@dataclass
class ApprovalManager:
    """Manages approval policies for an agent."""

    policies: list[ApprovalPolicy] = field(default_factory=list)

    def add_policy(self, policy: ApprovalPolicy) -> None:
        self.policies.append(policy)

    async def check_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        context: dict | None = None,
    ) -> ApprovalResult:
        ctx = context or {}
        for policy in self.policies:
            result = await policy.check(tool_name, arguments, ctx)
            if not result.approved:
                return result
        return ApprovalResult(approved=True)
