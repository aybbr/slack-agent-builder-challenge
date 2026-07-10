"""MCP server configuration for the Tracey agent.

Centralises all external MCP server setup — what servers the agent connects
*to* as a client.  (``mcp_server/server.py`` is the inbound side — what Tracey
exposes *to* other clients.)

To add a new MCP server:
  1. Add its config dict to ``build_mcp_servers()``.
  2. Add its tool namespace to ``_EXTERNAL_TOOL_NAMESPACES`` or (for
     conditional servers) the appropriate conditional block.
  3. Add any new Tracey-internal tool name to ``_TRACEY_TOOL_NAMES``.
"""

from __future__ import annotations

import logging

from claude_agent_sdk.types import McpHttpServerConfig

from tracey.agent.deps import TraceyDeps

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server URLs
# ---------------------------------------------------------------------------

_MERMAID_MCP_URL = "https://mcp.mermaid.ai/mcp"
_SLACK_MCP_URL = "https://mcp.slack.com/mcp"

# ---------------------------------------------------------------------------
# Tracey in-process tools (always available)
# ---------------------------------------------------------------------------

_TRACEY_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "mcp__tracey-tools__add_reaction",
        "mcp__tracey-tools__annotate_pr",
        "mcp__tracey-tools__get_last_change",
        "mcp__tracey-tools__get_migration_order",
        "mcp__tracey-tools__get_usage",
        "mcp__tracey-tools__render_diagram_to_slack",
        "mcp__tracey-tools__search_slack_threads",
    ]
)

# ---------------------------------------------------------------------------
# Always-on external server namespaces
# ---------------------------------------------------------------------------

_EXTERNAL_TOOL_NAMESPACES: list[str] = [
    "mcp__dbt__*",
    "mcp__mermaid__*",
]

# ---------------------------------------------------------------------------
# Conditional external server namespace (Slack MCP)
# ---------------------------------------------------------------------------

_SLACK_TOOL_NAMESPACE = "mcp__slack-mcp__*"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_mcp_servers(
    deps: TraceyDeps | None,
    tracey_tools_server: object,
    dbt_project_dir: str,
) -> tuple[dict, list[str]]:
    """Build MCP server configurations and allowed tool list.

    Returns ``(mcp_servers, allowed_tools)`` suitable for
    ``ClaudeAgentOptions``.  ``slack-mcp`` is only added when
    ``deps.user_token`` is available.
    """
    mcp_servers: dict = {
        "tracey-tools": tracey_tools_server,
        "dbt": {
            "type": "stdio",
            "command": "uvx",
            "args": ["dbt-mcp"],
            "env": {"DBT_PROJECT_DIR": dbt_project_dir},
        },
        "mermaid": McpHttpServerConfig(
            type="http",
            url=_MERMAID_MCP_URL,
        ),
    }

    allowed_tools = list(_TRACEY_TOOL_NAMES)
    allowed_tools.extend(_EXTERNAL_TOOL_NAMESPACES)

    if deps and deps.user_token:
        try:
            mcp_servers["slack-mcp"] = McpHttpServerConfig(
                type="http",
                url=_SLACK_MCP_URL,
                headers={"Authorization": f"Bearer {deps.user_token}"},
            )
            allowed_tools.append(_SLACK_TOOL_NAMESPACE)
        except Exception:
            logger.warning("Failed to configure Slack MCP server", exc_info=True)

    return mcp_servers, allowed_tools
