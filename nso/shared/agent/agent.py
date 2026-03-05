"""
Agent — the main orchestrator.

Combines model, tools, guardrails, memory, and approval into a single
configurable agent that can be instantiated and run.

Ported from chatagent's Agent class, adapted for NSO.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Any, Callable

from .model.base import Model
from .model.message import Message
from .tools.function import Function
from .tools.registry import ToolRegistry
from .tools.toolkit import Toolkit
from .run import run_agent_loop, RunEvent
from .cancel import RunCancellation
from .approval import ApprovalManager
from .guardrails import GuardrailChain, GuardrailAction

logger = logging.getLogger(__name__)


@dataclass
class Agent:
    """
    AI Agent — configurable, tool-using, streaming agent.

    Usage:
        agent = Agent(
            name="deploy",
            model=OpenAILike(id="llama-3.3-70b-versatile", ...),
            instructions=["Help deploy projects"],
            tools=[my_func],
        )

        async for event in agent.arun("Deploy my project"):
            print(event)
    """

    # Identity
    name: str = "agent"
    role: str = ""
    goal: str = ""
    backstory: str = ""

    # Model
    model: Model | None = None

    # Instructions (added to system prompt)
    instructions: list[str] = field(default_factory=list)
    system_prompt: str = ""  # Full override (if set, replaces auto-generated prompt)

    # Tools
    tools: list[Callable | Function] = field(default_factory=list)
    toolkits: list[Toolkit] = field(default_factory=list)

    # Execution
    max_steps: int = 15
    tool_choice: str | None = "auto"
    parallel_tool_execution: bool = True

    # Guardrails
    input_guardrails: GuardrailChain | None = None
    output_guardrails: GuardrailChain | None = None

    # Approval
    approval_manager: ApprovalManager | None = None

    # Output parsing
    response_format: str | None = None  # "json" for structured output
    expected_output: str = ""

    # Hooks
    on_run_start: Callable[..., Any] | None = None
    on_run_end: Callable[..., Any] | None = None
    on_tool_call: Callable[..., Any] | None = None

    # State
    _cancel_token: RunCancellation | None = field(default=None, init=False, repr=False)

    def build_system_prompt(self, extra_context: str = "") -> str:
        """Assemble the full system prompt from agent configuration."""
        if self.system_prompt:
            return self.system_prompt

        parts: list[str] = []

        # Role / persona
        if self.role:
            parts.append(f"You are {self.role}.")
        if self.goal:
            parts.append(f"\nYour goal: {self.goal}")
        if self.backstory:
            parts.append(f"\nBackground: {self.backstory}")

        # Instructions
        if self.instructions:
            parts.append("\n## Instructions")
            for instruction in self.instructions:
                parts.append(f"- {instruction}")

        # Expected output format
        if self.expected_output:
            parts.append(f"\n## Expected Output\n{self.expected_output}")

        if self.response_format == "json":
            parts.append("\n## Output Format\nRespond with valid JSON only.")

        # Extra context (e.g. from knowledge base)
        if extra_context:
            parts.append(f"\n## Context\n{extra_context}")

        # Datetime
        parts.append(f"\nCurrent datetime: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

        return "\n".join(parts)

    def build_registry(self) -> ToolRegistry:
        """Create a ToolRegistry from the agent's tools and toolkits."""
        registry = ToolRegistry()

        # Register toolkits
        for toolkit in self.toolkits:
            registry.register_toolkit(toolkit)

        # Register standalone tools
        for tool in self.tools:
            if isinstance(tool, Function):
                registry.register_function(tool)
            elif callable(tool):
                registry.register_callable(tool)

        return registry

    def cancel(self, reason: str = "user_cancelled") -> None:
        """Cancel any active run."""
        if self._cancel_token:
            self._cancel_token.cancel(reason=reason)

    async def arun(
        self,
        message: str,
        *,
        messages: list[Message] | None = None,
        extra_context: str = "",
        run_id: str = "",
    ) -> AsyncIterator[RunEvent]:
        """
        Run the agent with a user message, streaming events.

        Args:
            message: The user message to process.
            messages: Optional conversation history (if continuing a thread).
            extra_context: Additional context to inject into the system prompt.
            run_id: Unique ID for this run (auto-generated if empty).
        """
        if not self.model:
            yield RunEvent("error", {"error": "No model configured for agent"})
            return

        if not run_id:
            run_id = f"run_{uuid.uuid4().hex[:12]}"

        # Cancel token for this run
        self._cancel_token = RunCancellation(run_id=run_id)

        # Build conversation
        conversation = list(messages or [])
        conversation.append(Message.user(message))

        # Input guardrails
        if self.input_guardrails:
            guard_result = await self.input_guardrails.run(message)
            if guard_result.action == GuardrailAction.BLOCK:
                yield RunEvent("error", {
                    "error": f"Input blocked: {guard_result.message}",
                    "guardrail": guard_result.guardrail_name,
                })
                return
            if guard_result.action == GuardrailAction.MODIFY and guard_result.modified_content:
                conversation[-1] = Message.user(guard_result.modified_content)

        # Build system prompt and registry
        system_prompt = self.build_system_prompt(extra_context=extra_context)
        registry = self.build_registry()

        # on_run_start hook
        if self.on_run_start:
            result = self.on_run_start(run_id=run_id, message=message)
            if hasattr(result, "__await__"):
                await result

        # Run the loop
        final_text = ""
        async for event in run_agent_loop(
            model=self.model,
            messages=conversation,
            system_prompt=system_prompt,
            registry=registry,
            max_steps=self.max_steps,
            tool_choice=self.tool_choice,
            run_id=run_id,
            cancel_token=self._cancel_token,
            approval_manager=self.approval_manager,
            parallel_tool_execution=self.parallel_tool_execution,
        ):
            # on_tool_call hook
            if event.type == "tool_call" and self.on_tool_call:
                result = self.on_tool_call(**event.data)
                if hasattr(result, "__await__"):
                    await result

            if event.type == "status":
                final_text = event.data.get("final_text", "")

            yield event

        # Output guardrails
        if self.output_guardrails and final_text:
            guard_result = await self.output_guardrails.run(final_text)
            if guard_result.action == GuardrailAction.BLOCK:
                yield RunEvent("error", {
                    "error": f"Output blocked: {guard_result.message}",
                    "guardrail": guard_result.guardrail_name,
                })

        # on_run_end hook
        if self.on_run_end:
            result = self.on_run_end(run_id=run_id, final_text=final_text)
            if hasattr(result, "__await__"):
                await result

        self._cancel_token = None
