import logging
import os

from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from tracey.slack_agent.handlers import register_handlers

logger = logging.getLogger(__name__)

_SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

bolt_app = AsyncApp(
    token=_SLACK_BOT_TOKEN,
    signing_secret=_SLACK_SIGNING_SECRET,
)

register_handlers(bolt_app)

slack_handler = AsyncSlackRequestHandler(bolt_app)


async def health(request):
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route(
            "/slack/events",
            endpoint=slack_handler.handle,
            methods=["POST"],
        ),
        Route(
            "/slack/interactivity",
            endpoint=slack_handler.handle,
            methods=["POST"],
        ),
    ],
)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not _SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN environment variable is required.")
    if not _SLACK_SIGNING_SECRET:
        raise RuntimeError("SLACK_SIGNING_SECRET environment variable is required.")

    host = os.environ.get("SLACK_AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("SLACK_AGENT_PORT", os.environ.get("PORT", "8000")))

    logger.info("Starting Tracey Slack Agent on %s:%d", host, port)

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
