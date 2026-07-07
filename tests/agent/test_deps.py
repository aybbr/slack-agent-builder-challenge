"""Tests for TraceyDeps — dependency injection dataclass."""

from slack_sdk.web.async_client import AsyncWebClient

from tracey.agent.deps import TraceyDeps


class TestTraceyDeps:
    def itShould_construct_with_required_fields(self):
        deps = TraceyDeps(
            client=AsyncWebClient(),
            user_id="U123",
            channel_id="C456",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        assert deps.client is not None
        assert deps.user_id == "U123"
        assert deps.channel_id == "C456"
        assert deps.thread_ts == "ts.001"
        assert deps.message_ts == "ts.001"
        assert deps.user_token is None

    def itShould_default_user_token_to_None(self):
        deps = TraceyDeps(
            client=AsyncWebClient(),
            user_id="U123",
            channel_id="C456",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        assert deps.user_token is None

    def itShould_accept_optional_user_token(self):
        deps = TraceyDeps(
            client=AsyncWebClient(),
            user_id="U123",
            channel_id="C456",
            thread_ts="ts.001",
            message_ts="ts.001",
            user_token="xoxp-token",
        )
        assert deps.user_token == "xoxp-token"
