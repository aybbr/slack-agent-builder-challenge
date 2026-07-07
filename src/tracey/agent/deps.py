"""Runtime dependencies injected into agent tools via ContextVar."""

from dataclasses import dataclass

from slack_sdk.web.async_client import AsyncWebClient


@dataclass(slots=True)
class TraceyDeps:
    """Carries Slack API client and conversation context to agent tools."""

    client: AsyncWebClient
    user_id: str
    channel_id: str
    thread_ts: str
    message_ts: str
    user_token: str | None = None
