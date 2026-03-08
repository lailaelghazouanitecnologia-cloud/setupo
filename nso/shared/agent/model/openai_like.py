"""
OpenAI-compatible model implementation.

Works for any provider that implements the OpenAI Chat Completions API:
  - OpenAI, OpenRouter, Groq, Together, Fireworks, etc.

Uses the openai SDK for robust streaming and error handling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

from openai import AsyncOpenAI

from .base import Model
from .message import Message, ToolCall, ToolCallFunction
from .response import ModelResponse, Usage

logger = logging.getLogger(__name__)


@dataclass
class OpenAILike(Model):
    """
    OpenAI-compatible LLM model.

    Usage:
        model = OpenAILike(id="gpt-4o", api_key="sk-...")

        # Groq
        model = OpenAILike(
            id="llama-3.3-70b-versatile",
            api_key="gsk_...",
            base_url="https://api.groq.com/openai/v1",
            provider="groq",
        )

        # OpenRouter
        model = OpenAILike(
            id="anthropic/claude-sonnet-4-20250514",
            api_key="sk-or-...",
            base_url="https://openrouter.ai/api/v1",
            provider="openrouter",
        )
    """

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    default_headers: dict = field(default_factory=dict)
    provider: str = "openai"

    _client: AsyncOpenAI | None = field(default=None, init=False, repr=False)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers=self.default_headers or None,
                max_retries=self.max_retries,
                timeout=self.request_timeout,
            )
        return self._client

    async def ainvoke(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ModelResponse:
        params = self._build_params(messages, tools, tool_choice, stream=False)

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(**params)
                return self._parse_response(response)
            except Exception as e:
                if attempt == self.max_retries:
                    raise
                wait = self.retry_delay * (2 ** attempt)
                logger.warning("Model call failed (attempt %d), retrying in %.1fs: %s", attempt + 1, wait, e)
                await asyncio.sleep(wait)

        raise RuntimeError("Unreachable")

    async def ainvoke_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ModelResponse]:
        params = self._build_params(messages, tools, tool_choice, stream=True)

        # Retry on 400 errors (e.g. model generates invalid JSON in tool args)
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(**params)
                last_error = None
                break
            except Exception as e:
                error_str = str(e)
                # Retry on 400 "Invalid JSON" errors (model-generated bad tool args)
                if "400" in error_str and ("Invalid JSON" in error_str or "invalid_json" in error_str.lower()):
                    last_error = e
                    wait = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        "Model returned 400 (bad tool call JSON), retry %d/%d in %.1fs: %s",
                        attempt + 1, self.max_retries, wait, error_str[:200],
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        if last_error is not None:
            # All retries exhausted — try once more without tools as fallback
            logger.warning("All retries exhausted for 400 error, falling back to no-tools mode")
            params.pop("tools", None)
            params.pop("tool_choice", None)
            params.pop("parallel_tool_calls", None)
            # Strip tool messages from history (they cause 400 on some providers)
            params["messages"] = self._strip_tool_messages(params["messages"])
            stream = await self.client.chat.completions.create(**params)

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta
            response = ModelResponse(
                finish_reason=choice.finish_reason,
                model=chunk.model,
            )

            if delta and delta.content:
                response.content = delta.content

            if delta and getattr(delta, "reasoning", None):
                response.reasoning = delta.reasoning

            if delta and delta.tool_calls:
                response.tool_calls = []
                for tc in delta.tool_calls:
                    response.tool_calls.append(ToolCall(
                        id=tc.id or "",
                        type="function",
                        function=ToolCallFunction(
                            name=tc.function.name or "" if tc.function else "",
                            arguments=tc.function.arguments or "" if tc.function else "",
                        ),
                    ))

            if chunk.usage:
                response.usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens or 0,
                    completion_tokens=chunk.usage.completion_tokens or 0,
                    total_tokens=chunk.usage.total_tokens or 0,
                )

            yield response

    @staticmethod
    def _sanitize_messages(messages: list[Message]) -> list[dict]:
        """Sanitize messages for API submission.

        Ensures all tool_call arguments in historical messages are valid JSON,
        which some providers (e.g. Baseten) strictly validate on the request body.
        """
        import json as _json
        sanitized = []
        for m in messages:
            d = m.to_dict()
            if d.get("tool_calls"):
                clean_tcs = []
                for tc in d["tool_calls"]:
                    fn = tc.get("function", {})
                    args_str = fn.get("arguments", "{}")
                    # Validate arguments is valid JSON
                    try:
                        _json.loads(args_str)
                    except (ValueError, TypeError):
                        # Fix: wrap in valid JSON or default to empty
                        fn["arguments"] = "{}"
                    clean_tcs.append(tc)
                d["tool_calls"] = clean_tcs
            sanitized.append(d)
        return sanitized

    @staticmethod
    def _strip_tool_messages(messages: list[dict]) -> list[dict]:
        """Remove tool_calls and tool result messages for no-tools fallback."""
        result = []
        for m in messages:
            if m.get("role") == "tool":
                continue
            if m.get("tool_calls"):
                # Convert to plain assistant message with content
                cleaned = {"role": m["role"]}
                if m.get("content"):
                    cleaned["content"] = m["content"]
                else:
                    cleaned["content"] = "(called tools)"
                result.append(cleaned)
            else:
                result.append(m)
        return result

    def _build_params(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        tool_choice: str | None,
        stream: bool,
    ) -> dict:
        params: dict[str, Any] = {
            "model": self.id,
            "messages": self._sanitize_messages(messages),
            "stream": stream,
        }

        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.stop is not None:
            params["stop"] = self.stop
        if self.seed is not None:
            params["seed"] = self.seed

        if self.response_format:
            if isinstance(self.response_format, str):
                if self.response_format in ("json", "json_object"):
                    params["response_format"] = {"type": "json_object"}
                elif self.response_format == "text":
                    params["response_format"] = {"type": "text"}
            elif isinstance(self.response_format, dict):
                params["response_format"] = self.response_format

        if tools:
            params["tools"] = tools
            if tool_choice:
                params["tool_choice"] = tool_choice
            # Disable parallel tool calls — simplifies output for models that
            # struggle with generating valid JSON for multiple tool calls at once.
            params["parallel_tool_calls"] = False

        if stream:
            params["stream_options"] = {"include_usage": True}

        return params

    def _parse_response(self, response: Any) -> ModelResponse:
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    type="function",
                    function=ToolCallFunction(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ),
                )
                for tc in msg.tool_calls
            ]

        usage = None
        if response.usage:
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return ModelResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            model=response.model,
        )
