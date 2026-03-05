"""
Model response types.

Normalized format that the agent loop processes uniformly
regardless of provider (OpenAI, Anthropic, Groq, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .message import ToolCall


@dataclass
class Usage:
    """Token usage from a model call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def total_cost_estimate(self) -> float:
        """Rough cost estimate (default GPT-4o pricing, override per model)."""
        return (self.prompt_tokens * 2.5 + self.completion_tokens * 10.0) / 1_000_000

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ModelResponse:
    """
    Normalized response from any LLM provider.

    In streaming mode, each chunk is a partial ModelResponse
    with only the delta fields populated.
    """
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    model: str | None = None
    latency_ms: float | None = None
    cached: bool = False

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def is_done(self) -> bool:
        return self.finish_reason in ("stop", "end_turn")

    @property
    def needs_tool_execution(self) -> bool:
        return self.finish_reason == "tool_calls" or self.has_tool_calls

    @property
    def hit_length_limit(self) -> bool:
        return self.finish_reason == "length"

    def to_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.content is not None:
            d["content"] = self.content
        if self.reasoning is not None:
            d["reasoning"] = self.reasoning
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.finish_reason:
            d["finish_reason"] = self.finish_reason
        if self.usage:
            d["usage"] = self.usage.to_dict()
        if self.model:
            d["model"] = self.model
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        return d
