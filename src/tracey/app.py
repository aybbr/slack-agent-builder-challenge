import logging
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from tracey.mcp_server.server import (
    _SKIP_SIGNATURE,
    _SLACK_SIGNING_SECRET,
    SlackSignatureMiddleware,
    mcp,
)

logger = logging.getLogger(__name__)


async def health(request):
    return JSONResponse({"status": "ok"})


mcp_app = mcp.http_app(
    transport="http",
    path="/mcp",
    stateless_http=True,
    json_response=True,
)

app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/mcp", endpoint=SlackSignatureMiddleware(mcp_app), methods=["GET", "POST"]),
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

    host = os.environ.get("FASTMCP_HOST", "0.0.0.0")
    port = int(os.environ.get("FASTMCP_PORT", os.environ.get("PORT", "8000")))

    logger.info(
        "Starting Tracey on %s:%d (signature check: %s)",
        host,
        port,
        "disabled" if _SKIP_SIGNATURE else "enabled",
    )

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
