"""
Toolkit — base class for grouping related tools.

Subclass and use @tool decorator on methods to create toolkits.
"""

from __future__ import annotations

from .function import Function


class Toolkit:
    """
    Base class for grouping related tools.

    Example:
        class WebTools(Toolkit):
            name = "web_tools"

            @tool(description="Search the web")
            async def search(self, query: str) -> str:
                ...
    """

    name: str | None = None
    description: str | None = None

    def get_functions(self) -> list[Function]:
        """Discover all @tool methods and return Function objects."""
        functions: list[Function] = []
        for attr_name in dir(self):
            if attr_name.startswith("_"):
                continue
            method = getattr(self, attr_name, None)
            if callable(method) and getattr(method, "_is_tool", False):
                func = Function.from_callable(method)
                functions.append(func)
        return functions

    def get_tool_map(self) -> dict[str, Function]:
        return {f.name: f for f in self.get_functions()}

    def get_openai_schemas(self) -> list[dict]:
        return [f.to_openai_schema() for f in self.get_functions()]
