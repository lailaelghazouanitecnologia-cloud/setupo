"""
Anthropic native model implementation.

Uses httpx directly to call the Anthropic Messages API.
Supports extended thinking, streaming, and tool use.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

import httpx

from .base import Model
from .message import Message, ToolCall, ToolCallFunction
from .response import ModelResponse, Usage

logger = logging.getLogger(__name__)


@dataclass
class AnthropicModel(Model):
    """
    Anthropic native Messages API implementation.

    Usage:
        model = AnthropicModel(
            id="claude-sonnet-4-20250514",
            api_key="sk-ant-...",
        )
    """

    api_key: str = ""
    base_url: str = "https://api.anthropic.com"
    api_version: str = "2023-06-01"
    provider: str = "anthropic"

    # Anthropic-specific
    enable_thinking: bool = False
    thinking_budget: int = 10000

    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.api_version,
                    "content-type": "application/json",
                },
                timeout=self.request_timeout,
            )
        return self._client

    def _build_body(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        tool_choice: str | None,
        stream: bool,
    ) -> dict:
        system_text = ""
        conversation: list[dict] = []

        for msg in messages:
            if msg.role == "system":
                system_text = msg.content or ""
            elif msg.role == "tool":
                conversation.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "",
                        "content": msg.content or "",
                    }],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content: list[dict] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": args,
                    })
                conversation.append({"role": "assistant", "content": content})
            else:
                conversation.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })

        body: dict[str, Any] = {
            "model": self.id,
            "messages": conversation,
            "max_tokens": self.max_tokens or 4096,
            "stream": stream,
        }

        if system_text:
            body["system"] = system_text
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.top_p is not None:
            body["top_p"] = self.top_p

        if tools:
            anthropic_tools = []
            for t in tools:
                func = t.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object"}),
                })
            body["tools"] = anthropic_tools
            if tool_choice:
                if tool_choice == "auto":
                    body["tool_choice"] = {"type": "auto"}
                elif tool_choice == "required":
                    body["tool_choice"] = {"type": "any"}
                elif tool_choice == "none":
                    pass

        if self.enable_thinking:
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        return body

    async def ainvoke(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ModelResponse:
        body = self._build_body(messages, tools, tool_choice, stream=False)

        for attempt in range(self.max_retries + 1):
            try:
                resp = await self.client.post("/v1/messages", json=body)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data)
            except Exception as e:
                if attempt == self.max_retries:
                    raise
                wait = self.retry_delay * (2 ** attempt)
                logger.warning("Anthropic call failed (attempt %d), retrying in %.1fs: %s", attempt + 1, wait, e)
                await asyncio.sleep(wait)

        raise RuntimeError("Unreachable")

    async def ainvoke_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ModelResponse]:
        body = self._build_body(messages, tools, tool_choice, stream=True)

        async with self.client.stream("POST", "/v1/messages", json=body) as resp:
            resp.raise_for_status()

            current_tool_id = ""
            current_tool_name = ""
            tool_input_buffer = ""

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        current_tool_id = block.get("id", "")
                        current_tool_name = block.get("name", "")
                        tool_input_buffer = ""

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "")

                    if delta_type == "text_delta":
                        yield ModelResponse(content=delta.get("text", ""))
                    elif delta_type == "thinking_delta":
                        yield ModelResponse(reasoning=delta.get("thinking", ""))
                    elif delta_type == "input_json_delta":
                        tool_input_buffer += delta.get("partial_json", "")

                elif event_type == "content_block_stop":
                    if current_tool_name:
                        yield ModelResponse(
                            tool_calls=[ToolCall(
                                id=current_tool_id,
                                type="function",
                                function=ToolCallFunction(
                                    name=current_tool_name,
                                    arguments=tool_input_buffer,
                                ),
                            )],
                        )
                        current_tool_id = ""
                        current_tool_name = ""
                        tool_input_buffer = ""

                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    stop_reason = delta.get("stop_reason")
                    usage_data = event.get("usage", {})
                    yield ModelResponse(
                        finish_reason=self._map_stop_reason(stop_reason),
                        usage=Usage(
                            completion_tokens=usage_data.get("output_tokens", 0),
                        ) if usage_data else None,
                    )

                elif event_type == "message_start":
                    msg = event.get("message", {})
                    usage_data = msg.get("usage", {})
                    if usage_data:
                        yield ModelResponse(
                            usage=Usage(prompt_tokens=usage_data.get("input_tokens", 0)),
                            model=msg.get("model"),
                        )

    def _parse_response(self, data: dict) -> ModelResponse:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "thinking":
                reasoning_parts.append(block.get("thinking", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    type="function",
                    function=ToolCallFunction(
                        name=block.get("name", ""),
                        arguments=json.dumps(block.get("input", {})),
                    ),
                ))

        usage_data = data.get("usage", {})

        return ModelResponse(
            content="\n".join(content_parts) if content_parts else None,
            reasoning="\n".join(reasoning_parts) if reasoning_parts else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=self._map_stop_reason(data.get("stop_reason")),
            usage=Usage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            ),
            model=data.get("model"),
        )

    @staticmethod
    def _map_stop_reason(reason: str | None) -> str | None:
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
            "max_tokens": "length",
        }
        return mapping.get(reason or "", reason)
