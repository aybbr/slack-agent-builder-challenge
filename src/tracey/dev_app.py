"""Unified local-development entrypoint for both the MCP and Slack agent services.

Mounts FastMCP (with Slack signature verification) and Bolt (with async
HTTP handler) on a single Starlette app so that one ``uv run`` process
and one ngrok tunnel serve all routes.

In production (Railway), the two services are deployed separately:
    - ``tracey``  (``tracey.app:main``) — MCP service
    - ``slack-agent`` (``tracey.slack_agent.app:main``) — Slack agent
"""

import logging
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from tracey.mcp_server.server import (
    _SKIP_SIGNATURE,
    _SLACK_SIGNING_SECRET,
    SlackSignatureMiddleware,
    mcp,
)
from tracey.slack_agent.app import slack_handler

logger = logging.getLogger(__name__)

_DEV_SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

mcp_app = mcp.http_app(
    transport="http",
    path="/",
    stateless_http=True,
    json_response=True,
)


async def health(request):
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Mount("/mcp", app=SlackSignatureMiddleware(mcp_app)),
        Route("/slack/events", endpoint=slack_handler.handle, methods=["POST"]),
        Route("/slack/interactivity", endpoint=slack_handler.handle, methods=["POST"]),
    ],
    lifespan=mcp_app.lifespan,
)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not _SLACK_SIGNING_SECRET and not _SKIP_SIGNATURE:
        raise RuntimeError(
            "SLACK_SIGNING_SECRET environment variable is required. "
            "Set TRACEY_SKIP_SIGNATURE_CHECK=1 for local development."
        )
    if not _DEV_SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN environment variable is required.")

    host = os.environ.get("DEV_HOST", "0.0.0.0")
    port = int(os.environ.get("DEV_PORT", os.environ.get("PORT", "8000")))

    logger.info(
        "Starting Tracey (unified dev mode) on %s:%d (MCP + Slack agent)",
        host,
        port,
    )

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
