"""
Abstract Model base class.

All LLM provider implementations inherit from this.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

from .message import Message
from .response import ModelResponse

logger = logging.getLogger(__name__)


@dataclass
class Model(ABC):
    """
    Abstract base class for LLM providers.

    Subclass this and implement ainvoke() and ainvoke_stream()
    to add support for a new provider.
    """

    # Model identification
    id: str = ""
    name: str | None = None
    provider: str = "unknown"

    # Generation parameters
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | None = None
    seed: int | None = None

    # Response format
    response_format: dict[str, Any] | str | None = None

    # Retry configuration
    max_retries: int = 2
    retry_delay: float = 1.0
    request_timeout: float = 300.0

    # Response caching
    cache_response: bool = False
    cache_ttl: int = 300
    _cache: dict[str, tuple[float, ModelResponse]] = field(
        default_factory=dict, init=False, repr=False,
    )

    def _cache_key(self, messages: list[Message], tools: list[dict] | None, tool_choice: str | None) -> str:
        payload = json.dumps({
            "model": self.id,
            "messages": [m.to_dict() for m in messages],
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def _get_cached(self, key: str) -> ModelResponse | None:
        if not self.cache_response:
            return None
        entry = self._cache.get(key)
        if entry and (time.time() - entry[0]) < self.cache_ttl:
            return entry[1]
        if entry:
            del self._cache[key]
        return None

    def _set_cached(self, key: str, response: ModelResponse) -> None:
        if self.cache_response:
            self._cache[key] = (time.time(), response)
            if len(self._cache) > 100:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest]

    async def ainvoke_cached(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ModelResponse:
        """Non-streaming completion with caching."""
        if self.cache_response:
            key = self._cache_key(messages, tools, tool_choice)
            cached = self._get_cached(key)
            if cached:
                cached.cached = True
                return cached

        response = await self.ainvoke(messages, tools, tool_choice)

        if self.cache_response:
            self._set_cached(key, response)

        return response

    @abstractmethod
    async def ainvoke(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> ModelResponse:
        """Non-streaming completion."""
        ...

    @abstractmethod
    async def ainvoke_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ModelResponse]:
        """Streaming completion. Yields partial ModelResponse chunks."""
        ...
        if False:  # pragma: no cover
            yield ModelResponse()

    def count_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars/token heuristic)."""
        return len(text) // 4

    def count_message_tokens(self, messages: list[Message]) -> int:
        total = 0
        for msg in messages:
            total += 4
            if msg.content:
                total += self.count_tokens(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count_tokens(tc.function.name)
                    total += self.count_tokens(tc.function.arguments)
        return total

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id!r}, provider={self.provider!r})"
