"""Tests for agent/loop.py — run_tracey_agent integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tracey.agent.deps import TraceyDeps
from tracey.agent.loop import run_tracey_agent


def _build_mock_sdk_client(messages: list):
    """Build a mock SDK client whose ``receive_response()`` yields the given messages."""

    async def _gen():
        for msg in messages:
            yield msg

    client = MagicMock()
    client.query = AsyncMock()
    client.receive_response.return_value = _gen()

    mock_sdk = MagicMock()
    mock_sdk.__aenter__ = AsyncMock(return_value=client)
    mock_sdk.__aexit__ = AsyncMock(return_value=None)
    return mock_sdk, client


class TestRunTraceyAgent:
    @pytest.mark.anyio
    async def itShould_return_error_when_api_key_is_missing(self, mocker):
        mocker.patch("tracey.agent.loop._DEEPSEEK_API_KEY", "")
        response_text, session_id = await run_tracey_agent(
            "drop fct_sales_pipeline",
        )
        assert "DEEPSEEK_API_KEY" in response_text
        assert session_id is None

    @pytest.mark.anyio
    async def itShould_produce_response_when_agent_returns_text(self, mocker):
        mocker.patch("tracey.agent.loop._DEEPSEEK_API_KEY", "sk-test-key")
        mock_sdk, _ = _build_mock_sdk_client(
            [
                _mock_assistant_message("Impact analysis: 3 downstream models affected."),
                _mock_result_message("session-123"),
            ]
        )
        mocker.patch("tracey.agent.loop.ClaudeSDKClient", return_value=mock_sdk)

        deps = TraceyDeps(
            client=AsyncMock(),
            user_id="U123",
            channel_id="C123",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        response_text, session_id = await run_tracey_agent(
            "drop lead_score from fct_sales_pipeline",
            deps=deps,
        )
        assert "3 downstream" in response_text
        assert session_id == "session-123"

    @pytest.mark.anyio
    async def itShould_return_empty_when_agent_takes_no_action(self, mocker):
        mocker.patch("tracey.agent.loop._DEEPSEEK_API_KEY", "sk-test-key")
        mock_sdk, _ = _build_mock_sdk_client(
            [
                _mock_result_message("session-456"),
            ]
        )
        mocker.patch("tracey.agent.loop.ClaudeSDKClient", return_value=mock_sdk)

        deps = TraceyDeps(
            client=AsyncMock(),
            user_id="U123",
            channel_id="C123",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        response_text, session_id = await run_tracey_agent(
            "Hello world",
            deps=deps,
        )
        assert response_text == ""
        assert session_id == "session-456"

    @pytest.mark.anyio
    async def itShould_handle_sdk_error_gracefully(self, mocker):
        mocker.patch("tracey.agent.loop._DEEPSEEK_API_KEY", "sk-test-key")
        mocker.patch(
            "tracey.agent.loop.ClaudeSDKClient",
            side_effect=RuntimeError("SDK connection failed"),
        )

        deps = TraceyDeps(
            client=AsyncMock(),
            user_id="U123",
            channel_id="C123",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        response_text, session_id = await run_tracey_agent(
            "drop fct_sales_pipeline",
            deps=deps,
        )
        assert ":warning:" in response_text
        assert session_id is None

    @pytest.mark.anyio
    async def itShould_resume_existing_session(self, mocker):
        mocker.patch("tracey.agent.loop._DEEPSEEK_API_KEY", "sk-test-key")
        mock_sdk, _ = _build_mock_sdk_client(
            [
                _mock_assistant_message("Continuing analysis..."),
                _mock_result_message("session-continued"),
            ]
        )
        mock_constructor = mocker.patch(
            "tracey.agent.loop.ClaudeSDKClient",
            return_value=mock_sdk,
        )

        deps = TraceyDeps(
            client=AsyncMock(),
            user_id="U123",
            channel_id="C123",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        response_text, session_id = await run_tracey_agent(
            "what about the column lineage?",
            session_id="existing-session",
            deps=deps,
        )
        assert "Continuing" in response_text

        options = mock_constructor.call_args[0][0]
        assert options.resume == "existing-session"

    @pytest.mark.anyio
    async def itShould_concatenate_multiple_text_blocks(self, mocker):
        mocker.patch("tracey.agent.loop._DEEPSEEK_API_KEY", "sk-test-key")
        mock_sdk, _ = _build_mock_sdk_client(
            [
                _mock_assistant_message("First part. "),
                _mock_assistant_message("Second part."),
                _mock_result_message("session-multi"),
            ]
        )
        mocker.patch("tracey.agent.loop.ClaudeSDKClient", return_value=mock_sdk)

        deps = TraceyDeps(
            client=AsyncMock(),
            user_id="U123",
            channel_id="C123",
            thread_ts="ts.001",
            message_ts="ts.001",
        )
        response_text, _ = await run_tracey_agent(
            "drop fct_sales_pipeline",
            deps=deps,
        )
        assert response_text == "First part. \nSecond part."


def _mock_assistant_message(text: str):
    from claude_agent_sdk import AssistantMessage, TextBlock

    return AssistantMessage(model="deepseek-v4-pro", content=[TextBlock(text=text)])


def _mock_result_message(session_id: str):
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=50,
        is_error=False,
        num_turns=1,
        session_id=session_id,
    )
