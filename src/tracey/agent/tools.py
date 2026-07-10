"""Agent tool definitions — @tool-decorated wrappers around services/ functions.

Each tool is a thin wrapper that delegates to a services/ function and returns
a structured ``{"content": [{"type": "text", "text": ...}]}`` dict following the
Claude Agent SDK tool result protocol.

Context-aware tools retrieve ``TraceyDeps`` from ``tracey_deps_var`` at runtime.
"""

import base64
import json
import logging
import os

import aiohttp
from claude_agent_sdk import tool
from mcp.types import ToolAnnotations
from slack_sdk.errors import SlackApiError

from tracey.services.changelog_service import get_last_change
from tracey.services.github_service import annotate_pr
from tracey.services.lineage_service import get_migration_order
from tracey.services.usage_service import get_usage

logger = logging.getLogger(__name__)

_MANIFEST_PATH = os.environ.get("MANIFEST_PATH", "dbt_project/target/manifest.json")
_DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "data/demo.duckdb")
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

_MERMAID_INK_BASE = "https://mermaid.ink/img"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _json_result(data: dict | list | None, error: str | None = None) -> dict:
    """Build a standard tool result with JSON content."""
    payload = {"error": error} if error else data
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


# ---------------------------------------------------------------------------
# Tool: get_migration_order
# ---------------------------------------------------------------------------


@tool(
    name="get_migration_order",
    description=(
        "Get a topologically sorted migration plan for all downstream models "
        "of a given dbt model. Returns each descendant with its migration order "
        "number, domain, cross-domain flag, and whether it is the source model. "
        "Use this when planning how to sequence changes across dependent models."
    ),
    input_schema={"model": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def get_migration_order_tool(args: dict) -> dict:
    """Return migration order for the given model."""
    model = args["model"].strip()
    if not model:
        return _json_result(None, error="model is required")

    try:
        result = get_migration_order(model, _MANIFEST_PATH)
    except Exception as exc:
        logger.exception("get_migration_order failed for %s", model)
        return _json_result(None, error=str(exc))

    return _json_result(result)


# ---------------------------------------------------------------------------
# Tool: get_usage
# ---------------------------------------------------------------------------


@tool(
    name="get_usage",
    description=(
        "Get per-domain usage statistics for a dbt model, including query counts "
        "and dashboard counts aggregated by domain. Useful for understanding which "
        "teams depend on a model and how heavily it is used."
    ),
    input_schema={"model": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def get_usage_tool(args: dict) -> dict:
    """Return usage statistics for the given model."""
    model = args["model"].strip()
    if not model:
        return _json_result(None, error="model is required")

    try:
        result = get_usage(model, _DUCKDB_PATH)
    except Exception as exc:
        logger.exception("get_usage failed for %s", model)
        return _json_result(None, error=str(exc))

    return _json_result(result)


# ---------------------------------------------------------------------------
# Tool: get_last_change
# ---------------------------------------------------------------------------


@tool(
    name="get_last_change",
    description=(
        "Get the last schema change recorded for a dbt model. Returns the "
        "timestamp (ISO-8601), change type (e.g. column_drop, refactor, column_add), "
        "author, and a summary. Use this to detect stale past discussions."
    ),
    input_schema={"model": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def get_last_change_tool(args: dict) -> dict:
    """Return the last schema change for the given model."""
    model = args["model"].strip()
    if not model:
        return _json_result(None, error="model is required")

    try:
        result = get_last_change(model, _DUCKDB_PATH)
    except Exception as exc:
        logger.exception("get_last_change failed for %s", model)
        return _json_result(None, error=str(exc))

    return _json_result(result)


# ---------------------------------------------------------------------------
# Tool: annotate_pr
# ---------------------------------------------------------------------------


@tool(
    name="annotate_pr",
    description=(
        "Annotate a GitHub pull request with an impact analysis summary. "
        "Posts a comment on the specified PR. Requires that GITHUB_TOKEN and "
        "GITHUB_REPO environment variables are configured."
    ),
    input_schema={"pr_id": str, "summary": str},
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def annotate_pr_tool(args: dict) -> dict:
    """Annotate a GitHub PR with the given summary."""
    pr_id = args.get("pr_id", "").strip()
    summary = args.get("summary", "").strip()

    if not pr_id:
        return _json_result(None, error="pr_id is required")
    if not summary:
        return _json_result(None, error="summary is required")
    if not _GITHUB_TOKEN:
        return _json_result(None, error="GITHUB_TOKEN is not configured")
    if not _GITHUB_REPO:
        return _json_result(None, error="GITHUB_REPO is not configured")

    try:
        result = annotate_pr(pr_id, summary, _GITHUB_REPO, _GITHUB_TOKEN)
    except Exception as exc:
        logger.exception("annotate_pr failed for PR #%s", pr_id)
        return _json_result(None, error=str(exc))

    return _json_result(result)


# ---------------------------------------------------------------------------
# Tool: search_slack_threads
# ---------------------------------------------------------------------------


@tool(
    name="search_slack_threads",
    description=(
        "Search Slack for past threads mentioning a dbt model. Uses Slack's "
        "Real-Time Search API (assistant.search.context) with a user token. "
        "Returns messages with author, channel, permalink, timestamp, and "
        "context messages. Requires SLACK_USER_TOKEN to be configured."
    ),
    input_schema={"model": str},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def search_slack_threads_tool(args: dict) -> dict:
    """Search Slack RTS for threads mentioning the model."""
    from tracey.agent.context import tracey_deps_var

    model = args["model"].strip()
    if not model:
        return _json_result(None, error="model is required")

    deps = tracey_deps_var.get()
    if deps is None or not deps.user_token:
        return _json_result([], error="SLACK_USER_TOKEN not configured")
    try:
        from slack_sdk.web.async_client import AsyncWebClient

        rts_client = AsyncWebClient(token=deps.user_token)
        response = await rts_client.api_call(
            api_method="assistant.search.context",
            http_verb="POST",
            json={
                "query": model,
                "content_types": ["messages"],
                "channel_types": ["public_channel"],
                "sort": "timestamp",
                "sort_dir": "desc",
                "limit": 20,
            },
        )
        messages = response.get("results", {}).get("messages", [])
        return _json_result(messages)
    except SlackApiError as exc:
        logger.warning("Slack RTS search failed for %s: %s", model, exc)
        return _json_result([], error=str(exc))


# ---------------------------------------------------------------------------
# Tool: add_reaction
# ---------------------------------------------------------------------------


@tool(
    name="add_reaction",
    description=(
        "Add an emoji reaction to the current message. Use the standard Slack "
        "emoji name without colons (e.g. 'eyes', 'tada', 'warning'). For change "
        "proposals, use 'eyes' to show you're looking into it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "emoji_name": {
                "type": "string",
                "description": ("Slack emoji name without colons (e.g. 'eyes', 'tada', 'warning')"),
            },
        },
        "required": ["emoji_name"],
    },
    annotations=ToolAnnotations(readOnlyHint=False),
)
async def add_reaction_tool(args: dict) -> dict:
    """Add an emoji reaction to the triggering message."""
    from tracey.agent.context import tracey_deps_var

    emoji_name = args["emoji_name"]

    deps = tracey_deps_var.get()
    if deps is None:
        return _json_result(None, error="Slack client not available")

    try:
        await deps.client.reactions_add(
            channel=deps.channel_id,
            timestamp=deps.message_ts,
            name=emoji_name,
        )
        return {"content": [{"type": "text", "text": f"Reacted with :{emoji_name}:"}]}
    except SlackApiError as exc:
        logger.warning("Failed to add reaction :%s:: %s", emoji_name, exc)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not add reaction: {exc.response.get('error', str(exc))}",
                }
            ]
        }


# ---------------------------------------------------------------------------
# Tool: render_diagram_to_slack
# ---------------------------------------------------------------------------


@tool(
    name="render_diagram_to_slack",
    description=(
        "Render a Mermaid diagram as a PNG and post it as a card in the "
        "current Slack thread. You must provide the raw Mermaid syntax "
        "(e.g. 'flowchart TD\\n    A --> B') which you compose based on "
        "lineage data from dbt MCP. Call `validate_and_render_mermaid_diagram` "
        "(Mermaid MCP) BEFORE calling this tool to validate your syntax and "
        "obtain a playground link. The diagram card is posted automatically; "
        "reference it in your text response."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mermaid_syntax": {
                "type": "string",
                "description": "Raw Mermaid diagram syntax (e.g. 'flowchart TD\\n    A --> B')",
            },
            "title": {
                "type": "string",
                "description": "Card title for the diagram in Slack (e.g. 'Impact Lineage')",
            },
            "subtitle": {
                "type": "string",
                "description": (
                    "Optional mrkdwn subtitle for the card (e.g. '*fct_sales* → 3 downstream, 1 cross-domain')"
                ),
            },
            "playground_url": {
                "type": "string",
                "description": (
                    "Mermaid Chart playground link from "
                    "`validate_and_render_mermaid_diagram`.  Must be obtained "
                    "BEFORE calling this tool."
                ),
            },
        },
        "required": ["mermaid_syntax", "title"],
    },
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def render_diagram_to_slack_tool(args: dict) -> dict:
    """Render an agent-generated Mermaid diagram and post it as a Slack card."""
    from tracey.agent.context import tracey_deps_var

    mermaid_syntax = args["mermaid_syntax"].strip()
    title = args["title"].strip()
    playground_url = args.get("playground_url", "").strip()

    if not mermaid_syntax:
        return _json_result(None, error="mermaid_syntax is required")
    if not title:
        return _json_result(None, error="title is required")

    deps = tracey_deps_var.get()
    if deps is None:
        return _json_result(None, error="Slack client not available")

    encoded = base64.urlsafe_b64encode(mermaid_syntax.encode()).decode().rstrip("=")
    mermaid_url = f"{_MERMAID_INK_BASE}/{encoded}"

    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.get(mermaid_url)
            try:
                if resp.status != 200:
                    return _json_result(
                        {"mermaid_syntax": mermaid_syntax},
                        error=f"mermaid.ink returned HTTP {resp.status}",
                    )
                image_bytes = await resp.read()
            finally:
                resp.close()
    except aiohttp.ClientError as exc:
        logger.warning("mermaid.ink request failed: %s", exc)
        return _json_result(
            {"mermaid_syntax": mermaid_syntax},
            error=f"Failed to render diagram: {exc}",
        )

    filename = f"diagram_{deps.message_ts}.png"
    try:
        upload_result = await deps.client.files_upload_v2(
            channel=deps.channel_id,
            thread_ts=deps.thread_ts,
            file=image_bytes,
            filename=filename,
            title=title,
        )
    except SlackApiError as exc:
        logger.warning("Slack file upload failed: %s", exc)
        return _json_result(
            {"mermaid_syntax": mermaid_syntax},
            error=f"Failed to upload diagram to Slack: {exc}",
        )

    files = upload_result.get("files", [])
    file_url = files[0].get("permalink", "") if files else ""

    return _json_result(
        {
            "diagram_url": file_url or mermaid_url,
            "playground_url": playground_url or None,
        }
    )
