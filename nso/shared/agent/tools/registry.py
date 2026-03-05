"""
ToolRegistry — central registry for tools.

Collects Function objects from Toolkits and standalone callables.
Dispatches tool calls by name during the agent loop.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .function import Function, FunctionCall
from .toolkit import Toolkit

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for discovering, registering, and executing tools.

    The agent creates a ToolRegistry, registers its Toolkits,
    and passes the registry to the run loop for tool dispatch.
    """

    def __init__(self) -> None:
        self._functions: dict[str, Function] = {}

    def register_toolkit(self, toolkit: Toolkit) -> None:
        """Register all @tool methods from a Toolkit instance."""
        tool_map = toolkit.get_tool_map()
        self._functions.update(tool_map)
        logger.info(
            "Registered toolkit '%s' with tools: %s",
            type(toolkit).__name__,
            list(tool_map.keys()),
        )

    def register_function(self, function: Function) -> None:
        """Register a single Function."""
        self._functions[function.name] = function

    def register_callable(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """Register a standalone callable as a tool."""
        function = Function.from_callable(func, name=name, description=description)
        self._functions[function.name] = function

    @property
    def schemas(self) -> list[dict]:
        """OpenAI function-calling schemas for all registered tools."""
        return [f.to_openai_schema() for f in self._functions.values()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._functions.keys())

    def has_tools(self) -> bool:
        return len(self._functions) > 0

    def get_function(self, name: str) -> Function | None:
        return self._functions.get(name)

    async def execute(self, tool_name: str, arguments: dict[str, Any], call_id: str = "") -> FunctionCall:
        """Execute a tool by name. Returns FunctionCall with result or error."""
        call = FunctionCall(name=tool_name, arguments=arguments, call_id=call_id)

        function = self._functions.get(tool_name)
        if not function:
            call.error = f"Unknown tool: {tool_name}"
            return call

        await call.execute(function)
        return call
