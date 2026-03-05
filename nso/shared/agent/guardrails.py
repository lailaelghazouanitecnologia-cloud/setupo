"""
Guardrails — input/output safety validation.

Checks that run before (input) and after (output) agent execution
to ensure safety, compliance, and quality.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"
    WARN = "warn"
    ESCALATE = "escalate"


@dataclass
class GuardrailResult:
    passed: bool = True
    action: GuardrailAction = GuardrailAction.ALLOW
    message: str = ""
    modified_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    guardrail_name: str = ""

    @classmethod
    def allow(cls, message: str = "") -> GuardrailResult:
        return cls(passed=True, action=GuardrailAction.ALLOW, message=message)

    @classmethod
    def block(cls, message: str, guardrail: str = "") -> GuardrailResult:
        return cls(passed=False, action=GuardrailAction.BLOCK, message=message, guardrail_name=guardrail)

    @classmethod
    def modify(cls, original: str, modified: str, message: str = "") -> GuardrailResult:
        return cls(passed=True, action=GuardrailAction.MODIFY, modified_content=modified, message=message)

    @classmethod
    def warn(cls, message: str, guardrail: str = "") -> GuardrailResult:
        return cls(passed=True, action=GuardrailAction.WARN, message=message, guardrail_name=guardrail)


@dataclass
class Guardrail(ABC):
    """Abstract base for guardrails."""

    name: str = ""
    enabled: bool = True
    priority: int = 0  # Higher = runs first

    @abstractmethod
    async def check(self, content: str, context: dict[str, Any] | None = None) -> GuardrailResult:
        ...


@dataclass
class GuardrailChain:
    """
    A chain of guardrails executed in priority order.

    On BLOCK, execution stops immediately.
    On MODIFY, modified content passes to subsequent guardrails.
    """

    guardrails: list[Guardrail] = field(default_factory=list)

    def add(self, guardrail: Guardrail) -> None:
        self.guardrails.append(guardrail)
        self.guardrails.sort(key=lambda g: -g.priority)

    async def run(self, content: str, context: dict[str, Any] | None = None) -> GuardrailResult:
        current_content = content
        results: list[GuardrailResult] = []

        for guardrail in self.guardrails:
            if not guardrail.enabled:
                continue

            result = await guardrail.check(current_content, context)
            result.guardrail_name = guardrail.name
            results.append(result)

            if result.action == GuardrailAction.BLOCK:
                logger.warning("Guardrail '%s' BLOCKED: %s", guardrail.name, result.message)
                return result

            if result.action == GuardrailAction.MODIFY and result.modified_content:
                current_content = result.modified_content

            if result.action == GuardrailAction.WARN:
                logger.warning("Guardrail '%s' WARNING: %s", guardrail.name, result.message)

        return GuardrailResult.allow(message=f"Passed {len(results)} guardrails")
