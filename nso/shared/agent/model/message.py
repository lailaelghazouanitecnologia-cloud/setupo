"""
Message types for the model layer.

Role-based messages with tool calls and serialization to/from OpenAI format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCallFunction:
    """Function details within a tool call."""
    name: str = ""
    arguments: str = ""  # JSON string


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    id: str = ""
    type: str = "function"
    function: ToolCallFunction = field(default_factory=ToolCallFunction)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> ToolCall:
        func_data = d.get("function", {})
        return cls(
            id=d.get("id", ""),
            type=d.get("type", "function"),
            function=ToolCallFunction(
                name=func_data.get("name", ""),
                arguments=func_data.get("arguments", ""),
            ),
        )


@dataclass
class Message:
    """
    A conversation message.

    Supports all OpenAI Chat Completions roles: system, user,
    assistant (with optional tool_calls), and tool (with tool_call_id).
    """
    role: str = "user"
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict:
        """Serialize to OpenAI Chat Completions format."""
        d: dict[str, Any] = {"role": self.role}

        if self.content is not None:
            d["content"] = self.content

        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]

        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id

        if self.name:
            d["name"] = self.name

        return d

    @classmethod
    def from_dict(cls, d: dict) -> Message:
        """Deserialize from OpenAI Chat Completions format."""
        tool_calls = None
        if "tool_calls" in d and d["tool_calls"]:
            tool_calls = [ToolCall.from_dict(tc) for tc in d["tool_calls"]]

        return cls(
            role=d.get("role", "user"),
            content=d.get("content"),
            tool_calls=tool_calls,
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        )

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str | None = None, tool_calls: list[ToolCall] | None = None) -> Message:
        return cls(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> Message:
        return cls(role=MessageRole.TOOL, content=content, tool_call_id=tool_call_id)
