"""
Deploy Agent run loop — streams events via SSE.

Adapted from chatagent's run_agent_loop pattern.
Uses httpx for LLM calls (OpenAI-compatible API). No external SDK deps.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Any, Callable

import httpx

logger = logging.getLogger("nso.deploy_agent.run")


# ── Events ──

@dataclass
class RunEvent:
    type: str
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        payload = {"type": self.type}
        payload.update(self.data)
        return f"data: {json.dumps(payload, default=str)}\n\n"


# ── Function / Tool abstractions ──

@dataclass
class ToolFunction:
    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    callable: Callable | None = field(default=None, repr=False)

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @classmethod
    def from_callable(cls, func: Callable, name: str = "", description: str = "") -> ToolFunction:
        import inspect
        from typing import get_type_hints

        func_name = name or func.__name__
        func_desc = description or (func.__doc__ or "").strip()

        type_map = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}

        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        sig = inspect.signature(func)
        properties: dict[str, dict] = {}
        required: list[str] = []

        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            ptype = hints.get(pname, str)
            json_type = type_map.get(ptype, "string")
            prop: dict[str, Any] = {"type": json_type}

            param_descs = getattr(func, "_param_descriptions", {})
            if pname in param_descs:
                prop["description"] = param_descs[pname]

            properties[pname] = prop
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        return cls(
            name=func_name,
            description=func_desc,
            parameters={"type": "object", "properties": properties, "required": required},
            callable=func,
        )


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolFunction] = {}

    def register(self, func: Callable, name: str = "", description: str = ""):
        tool = ToolFunction.from_callable(func, name, description)
        self._tools[tool.name] = tool

    @property
    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def has_tools(self) -> bool:
        return len(self._tools) > 0

    async def execute(self, tool_name: str, args: dict) -> tuple[str, str | None]:
        """Execute tool, return (result_str, error_or_none)."""
        import inspect

        tool = self._tools.get(tool_name)
        if not tool or not tool.callable:
            err = f"Unknown tool: {tool_name}"
            return json.dumps({"error": err}), err

        try:
            result = tool.callable(**args)
            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, str):
                return result, None
            elif isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False, default=str), None
            else:
                return str(result), None
        except Exception as e:
            logger.exception("Tool '%s' failed", tool_name)
            err = str(e)
            return json.dumps({"error": f"Tool '{tool_name}' failed: {err}"}), err


# ── LLM streaming (OpenAI-compatible) ──

async def _stream_llm(
    api_key: str,
    api_url: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """Stream chunks from an OpenAI-compatible chat endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", api_url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                raise RuntimeError(f"LLM API error {resp.status_code}: {error_body.decode()[:500]}")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue


# ── Agent Run Loop ──

async def run_agent_loop(
    *,
    api_key: str,
    api_url: str,
    model: str,
    messages: list[dict],
    system_prompt: str,
    registry: ToolRegistry,
    max_steps: int = 10,
    run_id: str = "",
) -> AsyncIterator[RunEvent]:
    """
    Execute the deploy agent loop as an async generator.

    Streams RunEvents:
      thinking → text_chunk → tool_call → tool_result → ... → status(completed)
    """
    full_messages = [{"role": "system", "content": system_prompt}] + list(messages)
    tool_schemas = registry.schemas if registry.has_tools() else None
    final_text = ""

    for step in range(1, max_steps + 1):
        yield RunEvent("thinking", {"step": step, "run_id": run_id})
        logger.info("Run %s step %d/%d", run_id, step, max_steps)

        content_buffer = ""
        tool_calls_buffer: dict[int, dict] = {}
        finish_reason: str | None = None

        try:
            async for chunk in _stream_llm(api_key, api_url, model, full_messages, tool_schemas):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                fr = chunk.get("choices", [{}])[0].get("finish_reason")

                # Text content
                if delta.get("content"):
                    content_buffer += delta["content"]
                    yield RunEvent("text_chunk", {"content": delta["content"]})

                # Tool call deltas
                if delta.get("tool_calls"):
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.get("id"):
                            tool_calls_buffer[idx]["id"] = tc_delta["id"]
                        fn = tc_delta.get("function", {})
                        if fn.get("name"):
                            tool_calls_buffer[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_calls_buffer[idx]["arguments"] += fn["arguments"]

                if fr:
                    finish_reason = fr

        except Exception as e:
            logger.exception("LLM call failed at step %d", step)
            yield RunEvent("error", {"error": str(e)})
            yield RunEvent("status", {"content": "error", "final_text": content_buffer})
            return

        # ── Handle tool calls ──
        if tool_calls_buffer:
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if content_buffer:
                assistant_msg["content"] = content_buffer
            tc_list = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                tc_list.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })
            assistant_msg["tool_calls"] = tc_list
            full_messages.append(assistant_msg)

            # Execute each tool call
            for tc in tc_list:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                yield RunEvent("tool_call", {"id": tc["id"], "name": tool_name, "arguments": args})

                result_str, error = await registry.execute(tool_name, args)
                yield RunEvent("tool_result", {
                    "id": tc["id"], "name": tool_name,
                    "result": result_str[:3000],
                    "error": error,
                })

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str[:4000],
                })

            logger.info("Step %d: %d tool calls, auto-continuing", step, len(tc_list))
            continue  # auto-continue after tool calls

        # ── Completion ──
        if finish_reason in ("stop", "end_turn") or (content_buffer and not tool_calls_buffer):
            final_text = content_buffer
            full_messages.append({"role": "assistant", "content": content_buffer})
            yield RunEvent("status", {"content": "completed", "final_text": final_text, "steps": step})
            return

        # Length limit — continue
        if finish_reason == "length":
            full_messages.append({"role": "assistant", "content": content_buffer})
            continue

        # Unknown — treat as done
        final_text = content_buffer
        yield RunEvent("status", {"content": "completed", "final_text": final_text, "steps": step})
        return

    # Max steps
    yield RunEvent("status", {"content": "max_steps_reached", "final_text": final_text, "steps": max_steps})
