"""
Function — wraps a callable with its OpenAI function-calling schema.

Auto-generates JSON schema from Python type hints.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints

logger = logging.getLogger(__name__)

# ── Type hint → JSON Schema mapping ──

_TYPE_MAP: dict[type, dict] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    list: {"type": "array"},
    dict: {"type": "object"},
}


def _python_type_to_json_schema(t: Any) -> dict:
    """Convert a Python type hint to a JSON Schema type object."""
    if t in _TYPE_MAP:
        return dict(_TYPE_MAP[t])

    origin = getattr(t, "__origin__", None)
    if origin is list:
        args = getattr(t, "__args__", ())
        items = _python_type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}
    if origin is dict:
        return {"type": "object"}

    return {"type": "string"}


@dataclass
class Function:
    """
    A tool function definition.

    Wraps a callable with its OpenAI function-calling schema.
    """

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    callable: Callable | None = field(default=None, repr=False)

    def to_openai_schema(self) -> dict:
        """Generate OpenAI function-calling tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @classmethod
    def from_callable(
        cls,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
    ) -> Function:
        """Auto-generate a Function from a Python callable."""
        func_name = name or getattr(func, "_tool_name", None) or func.__name__
        func_desc = description or getattr(func, "_tool_description", None) or func.__doc__ or ""

        if func_desc:
            func_desc = func_desc.strip()

        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        sig = inspect.signature(func)
        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            if param_name == "return":
                continue

            param_type = hints.get(param_name, str)
            prop = _python_type_to_json_schema(param_type)

            param_descs: dict = getattr(func, "_tool_param_descriptions", {})
            if param_name in param_descs:
                prop["description"] = param_descs[param_name]

            properties[param_name] = prop

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return cls(
            name=func_name,
            description=func_desc,
            parameters={
                "type": "object",
                "properties": properties,
                "required": required,
            },
            callable=func,
        )


@dataclass
class FunctionCall:
    """
    A record of a tool function being called.

    Tracks the invocation arguments, result, and any errors.
    """

    name: str = ""
    arguments: dict = field(default_factory=dict)
    call_id: str = ""
    result: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.result is not None and self.error is None

    async def execute(self, function: Function) -> str:
        """Execute the function with stored arguments."""
        if not function.callable:
            self.error = f"Function '{self.name}' has no callable"
            return json.dumps({"error": self.error})

        try:
            result = function.callable(**self.arguments)
            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, str):
                self.result = result
            elif isinstance(result, (dict, list)):
                self.result = json.dumps(result, ensure_ascii=False, default=str)
            else:
                self.result = str(result)

            return self.result

        except Exception as e:
            self.error = str(e)
            logger.exception("FunctionCall '%s' failed", self.name)
            return json.dumps({"error": f"Tool '{self.name}' failed: {self.error}"})
