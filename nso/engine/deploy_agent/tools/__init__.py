"""
Deploy Agent tools — organized by domain.

Structure:
  tools/
  ├── __init__.py          ← This file: DeployContext + create_tools assembler
  ├── workspace.py         ← Workspace analysis, file ops, config generation, creation
  ├── deploy.py            ← Build, ship, status, validation
  ├── secrets.py           ← Secret listing and management
  ├── connectors.py        ← Connector setup and listing
  └── infrastructure.py    ← Instance creation, service mgmt, domain mgmt
"""

import logging

from nso.engine.deploy_agent.tools.workspace import create_workspace_tools
from nso.engine.deploy_agent.tools.deploy import create_deploy_tools
from nso.engine.deploy_agent.tools.secrets import create_secrets_tools
from nso.engine.deploy_agent.tools.connectors import create_connector_tools
from nso.engine.deploy_agent.tools.infrastructure import create_infrastructure_tools

logger = logging.getLogger("nso.deploy_agent.tools")


class DeployContext:
    """Shared context for all tool calls within a deploy session."""

    def __init__(self, project_id: str, user_id: str = "", workspace: str = ""):
        self.project_id = project_id
        self.user_id = user_id
        self.workspace = workspace


def create_tools(ctx: DeployContext) -> list[tuple]:
    """Create all deploy tools bound to a project context.

    Returns list of (callable, name, description) tuples.
    Each domain module contributes its own tools.
    """
    tools: list[tuple] = []
    tools += create_workspace_tools(ctx)
    tools += create_deploy_tools(ctx)
    tools += create_secrets_tools(ctx)
    tools += create_connector_tools(ctx)
    tools += create_infrastructure_tools(ctx)
    return tools
