import logging
import os

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from slack_sdk.signature import SignatureVerifier
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from tracey.services.changelog_service import get_last_change
from tracey.services.env_config import EnvConfig
from tracey.services.github_service import annotate_pr, close_pr
from tracey.services.lineage_service import get_migration_order
from tracey.services.usage_service import get_usage

logger = logging.getLogger(__name__)

_SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
_SKIP_SIGNATURE = os.environ.get("TRACEY_SKIP_SIGNATURE_CHECK", "").lower() in (
    "1",
    "true",
    "yes",
)


def _get_env() -> EnvConfig:
    """Return a cached snapshot of runtime environment configuration."""
    return EnvConfig.from_env()


def _require_asset_id(asset_id: str) -> dict | None:
    """Return ``{"error": ...}`` if ``asset_id`` is empty, else ``None``."""
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    return None


class SlackSignatureMiddleware:
    """ASGI middleware that verifies Slack request signatures.

    Every request to the MCP endpoint must include valid
    ``X-Slack-Signature`` and ``X-Slack-Request-Timestamp`` headers.
    Requests that fail verification receive a JSON-RPC 401 response.

    Set ``TRACEY_SKIP_SIGNATURE_CHECK=1`` to bypass verification
    during local development.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._verifier = SignatureVerifier(_SLACK_SIGNING_SECRET) if _SLACK_SIGNING_SECRET else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        body = await request.body()

        if not _SKIP_SIGNATURE and (
            self._verifier is None or not self._verifier.is_valid_request(body, dict(request.headers))
        ):
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": "Invalid request"},
                    "id": None,
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        async def _replay_receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        await self._app(scope, _replay_receive, send)


mcp = FastMCP("tracey")


@mcp.tool(
    name="get_migration_order",
    title="Get Migration Order",
    description=(
        "Return a topologically sorted migration plan for a dbt model "
        "and all its transitive downstream models. The order ensures "
        "that no model is migrated before its dependencies are ready. "
        "Includes cross-domain flags to highlight inter-team impact."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def tool_get_migration_order(asset_id: str) -> dict:
    if (err := _require_asset_id(asset_id)) is not None:
        return err
    return get_migration_order(asset_id.strip(), _get_env().manifest_path)


@mcp.tool(
    name="get_usage",
    title="Get Usage Statistics",
    description=(
        "Return aggregated usage statistics for a dbt model grouped by "
        "domain. Shows query counts and dashboard counts per domain "
        "plus overall totals. Helps assess who will be impacted by "
        "a schema change."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def tool_get_usage(asset_id: str) -> dict:
    if (err := _require_asset_id(asset_id)) is not None:
        return err
    return get_usage(asset_id.strip(), _get_env().duckdb_path)


@mcp.tool(
    name="get_last_change",
    title="Get Last Schema Change",
    description=(
        "Return the most recent schema change recorded for a dbt model. "
        "Includes the timestamp, change type, author, and summary. "
        "Use this to detect stale guidance — if a Slack thread about "
        "a model predates its last schema change, the thread's advice "
        "may be outdated."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def tool_get_last_change(asset_id: str) -> dict:
    if (err := _require_asset_id(asset_id)) is not None:
        return err
    return get_last_change(asset_id.strip(), _get_env().duckdb_path)


@mcp.tool(
    name="annotate_pr",
    title="Annotate Pull Request",
    description=(
        "Post a structured impact-analysis comment on a GitHub pull "
        "request. The summary should be Markdown-formatted and include "
        "lineage details, usage impact, migration order, and test "
        "breakages. Requires a valid GITHUB_TOKEN and GITHUB_REPO "
        "environment variable."
    ),
    annotations=ToolAnnotations(readOnlyHint=False),
)
def tool_annotate_pr(pr_id: str, summary: str) -> dict:
    if not pr_id or not pr_id.strip():
        return {"error": "pr_id must be a non-empty string"}
    if not summary or not summary.strip():
        return {"error": "summary must be a non-empty string"}
    env = _get_env()
    if not env.github_token or not env.github_repo:
        return {"error": ("GITHUB_TOKEN and GITHUB_REPO environment variables must be configured for PR annotation")}
    try:
        int(pr_id.strip())
    except ValueError:
        return {"error": f"Invalid PR number: {pr_id}"}
    return annotate_pr(pr_id.strip(), summary.strip(), env.github_repo, env.github_token)


@mcp.tool(
    name="close_pr",
    title="Close Pull Request",
    description=(
        "Close a GitHub pull request, optionally leaving a comment first. "
        "Use when a proposed change should not proceed as-is and the team "
        "should realign before opening a fresh PR. The branch is preserved, "
        "so the PR can be reopened. Requires a valid GITHUB_TOKEN and "
        "GITHUB_REPO environment variable."
    ),
    annotations=ToolAnnotations(readOnlyHint=False),
)
def tool_close_pr(pr_id: str, comment: str = "") -> dict:
    if not pr_id or not pr_id.strip():
        return {"error": "pr_id must be a non-empty string"}
    env = _get_env()
    if not env.github_token or not env.github_repo:
        return {"error": ("GITHUB_TOKEN and GITHUB_REPO environment variables must be configured to close a PR")}
    try:
        int(pr_id.strip())
    except ValueError:
        return {"error": f"Invalid PR number: {pr_id}"}
    return close_pr(pr_id.strip(), env.github_repo, env.github_token, comment=comment.strip() or None)
