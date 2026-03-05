"""
Deploy Agent run loop — re-exports from nso.shared.agent core.

This module previously contained an inline implementation.
Now delegates to the shared agent infrastructure for consistency.
"""

# Re-export the shared agent core for backward compatibility
from nso.shared.agent.run import RunEvent, RunResponse, run_agent_loop  # noqa: F401
from nso.shared.agent.tools import ToolRegistry  # noqa: F401
from nso.shared.agent.model import (  # noqa: F401
    Model, OpenAILike, AnthropicModel,
    Message, ModelResponse, Usage,
)
from nso.shared.agent.cancel import RunCancellation, CancellationManager, get_cancellation_manager  # noqa: F401
from nso.shared.agent.approval import ApprovalManager  # noqa: F401
