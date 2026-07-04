import logging
import os

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from slack_sdk.signature import SignatureVerifier
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from tracey.services.changelog_service import get_last_change
from tracey.services.github_service import annotate_pr
from tracey.services.lineage_service import (
    get_column_lineage,
    get_lineage,
    get_migration_order,
)
from tracey.services.test_service import get_tests
from tracey.services.usage_service import get_usage

logger = logging.getLogger(__name__)

_DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "data/demo.duckdb")
_MANIFEST_PATH = os.environ.get("MANIFEST_PATH", "dbt_project/target/manifest.json")
_DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "dbt_project")
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
_SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
_SKIP_SIGNATURE = (
    os.environ.get("TRACEY_SKIP_SIGNATURE_CHECK", "").lower() in ("1", "true", "yes")
)


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
        self._verifier = SignatureVerifier(_SLACK_SIGNING_SECRET)

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        body = await request.body()

        if not _SKIP_SIGNATURE and not self._verifier.is_valid_request(
            body, dict(request.headers)
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
    name="get_lineage",
    title="Get Model Lineage",
    description=(
        "Return upstream and downstream lineage for a dbt model. "
        "Shows which models depend on the given model and which models "
        "it depends on. Detects cross-domain dependencies (e.g. when a "
        "sales model is consumed by a finance model). "
        "Use this before changing or deprecating any model."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def tool_get_lineage(asset_id: str) -> dict:
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    return get_lineage(asset_id.strip(), _MANIFEST_PATH)


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
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    return get_migration_order(asset_id.strip(), _MANIFEST_PATH)


@mcp.tool(
    name="get_column_lineage",
    title="Get Column Lineage",
    description=(
        "Trace a specific column through all downstream dbt models using "
        "SQLGlot AST analysis. Detects how the column is used in each "
        "downstream model (SELECT clause, WHERE clause, JOIN condition, "
        "or expression). Returns the output column name at each step. "
        "Critical for understanding the full blast radius of a column "
        "removal or rename."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def tool_get_column_lineage(asset_id: str, column_name: str) -> dict:
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    if not column_name or not column_name.strip():
        return {"error": "column_name must be a non-empty string"}
    return get_column_lineage(
        asset_id.strip(), column_name.strip(), _MANIFEST_PATH, _DBT_PROJECT_DIR
    )


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
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    return get_usage(asset_id.strip(), _DUCKDB_PATH)


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
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    return get_last_change(asset_id.strip(), _DUCKDB_PATH)


@mcp.tool(
    name="get_tests",
    title="Get dbt Tests",
    description=(
        "Return all dbt tests that depend on a given model. Includes "
        "the test name, target column, test type (not_null, unique, "
        "accepted_values, relationships), and severity. Helps "
        "identify which data quality checks will break if the model "
        "schema changes."
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
def tool_get_tests(asset_id: str) -> dict:
    if not asset_id or not asset_id.strip():
        return {"error": "asset_id must be a non-empty string"}
    return get_tests(asset_id.strip(), _MANIFEST_PATH)


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
    if not _GITHUB_TOKEN or not _GITHUB_REPO:
        return {
            "error": (
                "GITHUB_TOKEN and GITHUB_REPO environment variables "
                "must be configured for PR annotation"
            )
        }
    try:
        int(pr_id.strip())
    except ValueError:
        return {"error": f"Invalid PR number: {pr_id}"}
    return annotate_pr(pr_id.strip(), summary.strip(), _GITHUB_REPO, _GITHUB_TOKEN)
