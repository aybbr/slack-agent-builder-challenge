"""Agent loop: configure and run Tracey via Claude Agent SDK.

MCP server configuration is delegated to ``agent/mcp_config.py`` so that
adding a new external server does not require touching the agent loop.
"""

import logging
import os
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
)

from tracey.agent.context import tracey_deps_var
from tracey.agent.deps import TraceyDeps
from tracey.agent.mcp_config import build_mcp_servers
from tracey.agent.system_prompt import TRACEY_SYSTEM_PROMPT
from tracey.agent.tools import (
    add_reaction_tool,
    annotate_pr_tool,
    get_last_change_tool,
    get_migration_order_tool,
    get_usage_tool,
    render_diagram_to_slack_tool,
    search_slack_threads_tool,
)

logger = logging.getLogger(__name__)

_DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
_ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
_DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "dbt_project")

_MODEL = "deepseek-v4-pro"

# Wire auth env vars once at import time so the Claude Agent SDK
# (Claude Code binary) picks them up without per-call os.environ mutation.
if _DEEPSEEK_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = _DEEPSEEK_API_KEY
    os.environ["ANTHROPIC_AUTH_TOKEN"] = _DEEPSEEK_API_KEY
if not os.environ.get("ANTHROPIC_BASE_URL"):
    os.environ["ANTHROPIC_BASE_URL"] = _ANTHROPIC_BASE_URL

tracey_tools_server = create_sdk_mcp_server(
    name="tracey-tools",
    version="1.0.0",
    tools=[
        get_migration_order_tool,
        get_usage_tool,
        get_last_change_tool,
        annotate_pr_tool,
        search_slack_threads_tool,
        add_reaction_tool,
        render_diagram_to_slack_tool,
    ],
)


async def run_tracey_agent(
    text: str,
    session_id: str | None = None,
    deps: TraceyDeps | None = None,
) -> tuple[str, str | None]:
    """Run the Tracey agent with the given message and optional session.

    Args:
        text: The channel message text to evaluate.
        session_id: Resume a previous conversation. ``None`` for a new thread.
        deps: Runtime dependencies for tools (Slack client + context).

    Returns:
        ``(response_text, new_session_id)`` — ``response_text`` may be empty
        if the agent determines no action is needed.
    """
    if not _DEEPSEEK_API_KEY:
        return (
            ":warning: DEEPSEEK_API_KEY is not configured. Agent cannot run without an API key.",
            None,
        )

    if deps:
        tracey_deps_var.set(deps)

    mcp_servers, allowed_tools = build_mcp_servers(
        deps=deps,
        tracey_tools_server=tracey_tools_server,
        dbt_project_dir=str(Path(_DBT_PROJECT_DIR).absolute()),
    )

    options = ClaudeAgentOptions(
        system_prompt=TRACEY_SYSTEM_PROMPT,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        model=_MODEL,
        cwd=os.getcwd(),
    )

    if session_id:
        options.resume = session_id

    channel_id = deps.channel_id if deps else "?"
    logger.info(
        "Running Tracey agent — channel=%s model=%s session=%s",
        channel_id,
        _MODEL,
        session_id or "new",
    )

    response_parts: list[str] = []
    new_session_id: str | None = None

    try:
        async with ClaudeSDKClient(options) as client:
            await client.query(text)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                if isinstance(message, ResultMessage):
                    new_session_id = message.session_id
    except Exception as exc:
        logger.exception("Agent invocation failed")
        return (
            f":warning: Agent error: {exc}",
            None,
        )

    response_text = "\n".join(response_parts) if response_parts else ""

    if response_text:
        logger.info("Agent response: %d chars", len(response_text))
        if "Failed to authenticate" in response_text or "401" in response_text:
            logger.error("Agent returned auth error: %s", response_text[:300])
    else:
        logger.info("Agent returned empty response (no action needed)")

    return response_text, new_session_id
