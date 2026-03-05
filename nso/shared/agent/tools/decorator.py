"""
@tool decorator — marks a method as a callable tool.

Schema is auto-generated from type hints when the Toolkit registers.
"""

from typing import Callable


def tool(
    description: str = "",
    name: str | None = None,
    param_descriptions: dict[str, str] | None = None,
) -> Callable:
    """
    Decorator to mark a method as a callable tool.

    Args:
        description: What the tool does (shown to the LLM).
        name: Override the tool name (defaults to method name).
        param_descriptions: Descriptions for each parameter.
    """
    def decorator(func: Callable) -> Callable:
        func._is_tool = True  # type: ignore[attr-defined]
        func._tool_name = name or func.__name__  # type: ignore[attr-defined]
        func._tool_description = description or func.__doc__ or ""  # type: ignore[attr-defined]
        if param_descriptions:
            func._tool_param_descriptions = param_descriptions  # type: ignore[attr-defined]
        return func
    return decorator
