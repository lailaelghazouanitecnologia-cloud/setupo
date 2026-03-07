"""
Agent run loop — the execution engine.

Orchestrates the cycle:
  1. Call model with conversation + tools
  2. Stream text to client
  3. If model requests tool calls → execute → inject results → loop
  4. If model finishes → complete
  5. If max_steps → force complete
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

from .model.base import Model
from .model.message import Message, ToolCall, ToolCallFunction
from .model.response import ModelResponse
from .tools.registry import ToolRegistry
from .cancel import RunCancellation
from .approval import ApprovalManager

logger = logging.getLogger(__name__)


@dataclass
class RunEvent:
    """
    An event emitted during an agent run.

    Event types:
      - thinking:        Agent is starting a new step
      - text_chunk:      Incremental text from the model
      - reasoning_chunk: Model reasoning/thinking (extended thinking)
      - tool_call:       Agent is calling a tool
      - tool_result:     Tool returned a result
      - tool_denied:     Tool call denied by approval policy
      - status:          Run status update (completed, error, max_steps)
      - error:           An error occurred
    """
    type: str
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        """Convert to SSE-compatible string for streaming."""
        payload = {"type": self.type}
        payload.update(self.data)
        return f"data: {json.dumps(payload, default=str)}\n\n"


@dataclass
class RunResponse:
    """Final result of an agent run."""
    run_id: str = ""
    content: str = ""
    steps: int = 0
    status: str = "completed"
    tool_calls_made: int = 0


async def _execute_single_tool(
    registry: ToolRegistry,
    tool_name: str,
    args: dict,
    call_id: str,
) -> tuple[str, str | None]:
    """Execute a single tool. Returns (result_str, error_or_none)."""
    call_result = await registry.execute(tool_name, args, call_id=call_id)
    result_str = call_result.result or json.dumps({"error": call_result.error})
    return result_str, call_result.error


async def run_agent_loop(
    *,
    model: Model,
    messages: list[Message],
    system_prompt: str,
    registry: ToolRegistry,
    max_steps: int = 15,
    tool_choice: str | None = "auto",
    run_id: str = "",
    cancel_token: RunCancellation | None = None,
    approval_manager: ApprovalManager | None = None,
    parallel_tool_execution: bool = True,
) -> AsyncIterator[RunEvent]:
    """
    Execute the full agent loop as an async generator.

    Streams events as the agent processes:
    thinking → LLM call → tool calls → repeat → status(completed).
    """
    full_messages: list[Message] = [Message.system(system_prompt)] + list(messages)
    tool_schemas = registry.schemas if registry.has_tools() else None
    final_text = ""

    if tool_schemas:
        logger.debug("Tool schemas (%d tools): %s", len(tool_schemas), [t.get("function", {}).get("name", "MISSING") for t in tool_schemas])
        for ts in tool_schemas:
            fn = ts.get("function", {})
            if not fn.get("name"):
                logger.error("Tool schema missing name! Schema: %s", json.dumps(ts)[:500])

    for step in range(1, max_steps + 1):
        # Check cancellation
        if cancel_token and cancel_token.is_cancelled:
            yield RunEvent("status", {
                "content": "cancelled",
                "final_text": final_text,
                "steps": step - 1,
                "cancel_reason": cancel_token.cancel_reason,
            })
            return

        yield RunEvent("thinking", {"step": step, "run_id": run_id})
        logger.info("Run %s step %d/%d", run_id, step, max_steps)

        # Stream LLM response
        content_buffer = ""
        reasoning_buffer = ""
        tool_calls_buffer: dict[int, dict] = {}
        finish_reason: str | None = None

        try:
            async for chunk in model.ainvoke_stream(
                messages=full_messages,
                tools=tool_schemas,
                tool_choice=tool_choice if tool_schemas else None,
            ):
                if chunk.content:
                    content_buffer += chunk.content
                    yield RunEvent("text_chunk", {"content": chunk.content})

                if chunk.reasoning:
                    reasoning_buffer += chunk.reasoning
                    yield RunEvent("reasoning_chunk", {"reasoning": chunk.reasoning})

                if chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        idx: int | None = None

                        if tc.id:
                            for existing_idx, existing in tool_calls_buffer.items():
                                if existing["id"] == tc.id:
                                    idx = existing_idx
                                    break
                            if idx is None:
                                idx = len(tool_calls_buffer)
                                tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                        else:
                            if tool_calls_buffer:
                                idx = max(tool_calls_buffer.keys())
                            else:
                                idx = 0
                                tool_calls_buffer[idx] = {"id": "", "name": "", "arguments": ""}

                        if tc.id:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function.name:
                            tool_calls_buffer[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments

                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason

        except Exception as e:
            logger.exception("Model call failed at step %d", step)
            yield RunEvent("error", {"error": str(e)})
            yield RunEvent("status", {"content": "error", "final_text": content_buffer})
            return

        # Handle tool calls
        if tool_calls_buffer:
            tool_calls_list: list[ToolCall] = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc_data = tool_calls_buffer[idx]
                tool_calls_list.append(ToolCall(
                    id=tc_data["id"],
                    type="function",
                    function=ToolCallFunction(
                        name=tc_data["name"],
                        arguments=tc_data["arguments"],
                    ),
                ))

            assistant_msg = Message.assistant(
                content=content_buffer or None,
                tool_calls=tool_calls_list,
            )
            full_messages.append(assistant_msg)

            # Parse and validate tool calls
            parsed_calls: list[tuple[ToolCall, dict]] = []
            for tc in tool_calls_list:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    error_msg = json.dumps({
                        "error": f"Failed to parse tool call arguments as JSON. "
                        f"Raw: {tc.function.arguments[:500]}"
                    })
                    yield RunEvent("tool_call", {"id": tc.id, "name": tool_name, "arguments": {}})
                    yield RunEvent("tool_result", {"id": tc.id, "name": tool_name, "result": error_msg[:2000]})
                    full_messages.append(Message.tool_result(tool_call_id=tc.id, content=error_msg))
                    continue
                parsed_calls.append((tc, args))

            # Approval checks
            approved_calls: list[tuple[ToolCall, dict]] = []
            for tc, args in parsed_calls:
                yield RunEvent("tool_call", {"id": tc.id, "name": tc.function.name, "arguments": args})

                if approval_manager:
                    approval_result = await approval_manager.check_tool_call(
                        tc.function.name, args, context={"run_id": run_id, "step": step},
                    )
                    if not approval_result.approved:
                        denied_msg = f"Tool '{tc.function.name}' denied: {approval_result.message}"
                        yield RunEvent("tool_denied", {"id": tc.id, "name": tc.function.name, "reason": approval_result.message})
                        full_messages.append(Message.tool_result(tool_call_id=tc.id, content=json.dumps({"error": denied_msg})))
                        continue

                approved_calls.append((tc, args))

            # Execute tool calls (parallel or sequential)
            if parallel_tool_execution and len(approved_calls) > 1:
                tasks = [
                    _execute_single_tool(registry, tc.function.name, args, tc.id)
                    for tc, args in approved_calls
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for (tc, args), result in zip(approved_calls, results):
                    if isinstance(result, Exception):
                        result_str = json.dumps({"error": str(result)})
                    else:
                        result_str = result[0]

                    yield RunEvent("tool_result", {"id": tc.id, "name": tc.function.name, "result": result_str[:2000]})
                    full_messages.append(Message.tool_result(tool_call_id=tc.id, content=result_str[:4000]))
            else:
                for tc, args in approved_calls:
                    result_str, _ = await _execute_single_tool(registry, tc.function.name, args, tc.id)
                    yield RunEvent("tool_result", {"id": tc.id, "name": tc.function.name, "result": result_str[:2000]})
                    full_messages.append(Message.tool_result(tool_call_id=tc.id, content=result_str[:4000]))

            continue  # Auto-continue

        # Handle completion
        if finish_reason in ("stop", "end_turn") or (content_buffer and not tool_calls_buffer):
            final_text = content_buffer
            full_messages.append(Message.assistant(content=content_buffer))

            yield RunEvent("status", {
                "content": "completed",
                "final_text": final_text,
                "steps": step,
            })
            return

        # Handle length limit
        elif finish_reason == "length":
            full_messages.append(Message.assistant(content=content_buffer))
            continue

        # Unknown — treat as done
        else:
            final_text = content_buffer
            yield RunEvent("status", {
                "content": "completed",
                "final_text": final_text,
                "steps": step,
            })
            return

    # Max steps reached
    yield RunEvent("status", {
        "content": "max_steps_reached",
        "final_text": final_text,
        "steps": max_steps,
    })
