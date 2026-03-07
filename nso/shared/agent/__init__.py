"""
NSO Agent Core — reusable AI agent infrastructure.

Ported from chatagent's MMS core. No Supabase, no external vector DB.
Uses SQLite for persistence (consistent with NSO's stack).

Usage:
    from nso.shared.agent import Agent, OpenAILike, AnthropicModel
    from nso.shared.agent.tools import tool, Toolkit, ToolRegistry

    agent = Agent(
        name="deploy",
        model=OpenAILike(id="llama-3.3-70b-versatile", api_key="..."),
        tools=[my_tool_func],
        instructions=["Help the user deploy their project"],
    )

    async for event in agent.arun("Deploy my project"):
        print(event)
"""

from nso.shared.agent.agent import Agent
from nso.shared.agent.run import run_agent_loop, run_dual_agent_loop, RunEvent, RunResponse
from nso.shared.agent.cancel import RunCancellation, CancellationManager, get_cancellation_manager
from nso.shared.agent.approval import (
    ApprovalManager, ApprovalPolicy, RequireApproval, AuditOnly,
    ApprovalRequest, ApprovalResult,
)
from nso.shared.agent.guardrails import (
    Guardrail, GuardrailChain, GuardrailResult, GuardrailAction,
)
from nso.shared.agent.model import (
    Model, OpenAILike, AnthropicModel,
    Message, ModelResponse, Usage,
)
from nso.shared.agent.tools import (
    tool, Toolkit, ToolRegistry, Function, FunctionCall,
)

__all__ = [
    "Agent",
    "run_agent_loop", "run_dual_agent_loop", "RunEvent", "RunResponse",
    "RunCancellation", "CancellationManager", "get_cancellation_manager",
    "ApprovalManager", "ApprovalPolicy", "RequireApproval", "AuditOnly",
    "ApprovalRequest", "ApprovalResult",
    "Guardrail", "GuardrailChain", "GuardrailResult", "GuardrailAction",
    "Model", "OpenAILike", "AnthropicModel",
    "Message", "ModelResponse", "Usage",
    "tool", "Toolkit", "ToolRegistry", "Function", "FunctionCall",
]
