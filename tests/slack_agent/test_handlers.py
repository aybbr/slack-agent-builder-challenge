import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tracey.slack_agent.handlers as handlers_module
from tracey.slack_agent.handlers import (
    PROCESSED_MESSAGES,
    handle_message,
    handle_start_cross_team_review,
    handle_generate_migration_plan,
    handle_mark_as_outdated,
    handle_annotate_pr,
    handle_annotate_pr_submission,
)


def _action_body(model="fct_sales_pipeline", user_id="U999"):
    return {
        "user": {"id": user_id},
        "channel": {"id": "C123"},
        "message": {"thread_ts": "1234567890.123456"},
        "trigger_id": "trig_123",
        "actions": [
            {
                "value": json.dumps({
                    "model": model,
                    "channel_id": "C123",
                    "message_ts": "1234567890.123456",
                }),
            },
        ],
    }


def _message_event(text="drop fct_sales_pipeline", channel="C123", ts="1234567890.123456"):
    return {
        "channel": channel,
        "ts": ts,
        "text": text,
        "subtype": None,
        "bot_id": None,
    }


@pytest.fixture(autouse=True)
def _clear_state():
    """Reset module-level state between tests."""
    PROCESSED_MESSAGES.clear()
    handlers_module._ANALYSIS_CACHE.clear()


@pytest.fixture
def _populate_cache(sample_analysis):
    key = ("C123", "1234567890.123456")
    handlers_module._ANALYSIS_CACHE[key] = sample_analysis


# ---- Message handler ----


class TestHandleMessage:
    @pytest.mark.anyio
    async def itShouldnt_respond_to_bot_messages(self, mock_slack_client):
        event = {
            "channel": "C123",
            "ts": "1234567890.123456",
            "text": "drop fct_sales_pipeline",
            "subtype": None,
            "bot_id": "B999",
        }
        await handle_message(
            event, mock_slack_client, AsyncMock(), {"bot_user_id": "B999"},
        )
        mock_slack_client.reactions_add.assert_not_called()

    @pytest.mark.anyio
    async def itShouldnt_respond_to_edited_messages(self, mock_slack_client):
        event = {
            "channel": "C123",
            "ts": "1234567890.123456",
            "text": "drop fct_sales_pipeline",
            "subtype": "message_changed",
        }
        await handle_message(
            event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"},
        )
        mock_slack_client.reactions_add.assert_not_called()

    @pytest.mark.anyio
    async def itShould_add_eyes_reaction_on_trigger(self, mock_slack_client, mocker):
        mocker.patch.object(
            handlers_module, "get_lineage",
            return_value={"asset_id": "fct_sales_pipeline", "domain": "sales",
                          "upstream": [], "downstream": []},
        )
        mocker.patch.object(
            handlers_module, "get_migration_order",
            return_value={"asset_id": "fct_sales_pipeline",
                          "migration_order": []},
        )
        mocker.patch.object(
            handlers_module, "get_usage",
            return_value={"asset_id": "fct_sales_pipeline", "by_domain": [],
                          "total_queries": 0, "total_dashboards": 0},
        )
        mocker.patch.object(
            handlers_module, "get_last_change",
            return_value={"asset_id": "fct_sales_pipeline", "last_change": None},
        )
        mocker.patch.object(
            handlers_module, "get_tests",
            return_value={"asset_id": "fct_sales_pipeline", "tests": [],
                          "referential_tests": []},
        )
        mocker.patch.object(
            handlers_module, "_search_slack_threads",
            return_value=[],
        )

        event = _message_event()
        await handle_message(
            event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"},
        )
        mock_slack_client.reactions_add.assert_called_once_with(
            channel="C123", timestamp="1234567890.123456", name="eyes",
        )

    @pytest.mark.anyio
    async def itShould_post_impact_card_on_trigger(self, mock_slack_client, mocker):
        mocker.patch.object(
            handlers_module, "get_lineage",
            return_value={"asset_id": "fct_sales_pipeline", "domain": "sales",
                          "upstream": [], "downstream": []},
        )
        mocker.patch.object(
            handlers_module, "get_migration_order",
            return_value={"asset_id": "fct_sales_pipeline",
                          "migration_order": []},
        )
        mocker.patch.object(
            handlers_module, "get_usage",
            return_value={"asset_id": "fct_sales_pipeline", "by_domain": [],
                          "total_queries": 0, "total_dashboards": 0},
        )
        mocker.patch.object(
            handlers_module, "get_last_change",
            return_value={"asset_id": "fct_sales_pipeline", "last_change": None},
        )
        mocker.patch.object(
            handlers_module, "get_tests",
            return_value={"asset_id": "fct_sales_pipeline", "tests": [],
                          "referential_tests": []},
        )
        mocker.patch.object(
            handlers_module, "_search_slack_threads",
            return_value=[],
        )

        event = _message_event()
        await handle_message(
            event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"},
        )
        assert mock_slack_client.chat_postMessage.call_count >= 1
        call_args = mock_slack_client.chat_postMessage.call_args_list[0]
        assert call_args.kwargs.get("blocks") is not None

    @pytest.mark.anyio
    async def itShouldnt_reprocess_same_message(self, mock_slack_client, mocker):
        mocker.patch.object(
            handlers_module, "get_lineage",
            return_value={"asset_id": "fct_sales_pipeline", "domain": "sales",
                          "upstream": [], "downstream": []},
        )
        mocker.patch.object(
            handlers_module, "get_migration_order",
            return_value={"asset_id": "fct_sales_pipeline",
                          "migration_order": []},
        )
        mocker.patch.object(
            handlers_module, "get_usage",
            return_value={"asset_id": "fct_sales_pipeline", "by_domain": [],
                          "total_queries": 0, "total_dashboards": 0},
        )
        mocker.patch.object(
            handlers_module, "get_last_change",
            return_value={"asset_id": "fct_sales_pipeline", "last_change": None},
        )
        mocker.patch.object(
            handlers_module, "get_tests",
            return_value={"asset_id": "fct_sales_pipeline", "tests": [],
                          "referential_tests": []},
        )
        mocker.patch.object(
            handlers_module, "_search_slack_threads",
            return_value=[],
        )

        event = _message_event()
        await handle_message(event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"})
        call_count = mock_slack_client.chat_postMessage.call_count
        await handle_message(event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"})
        assert mock_slack_client.chat_postMessage.call_count == call_count

    @pytest.mark.anyio
    async def itShouldnt_respond_to_non_trigger_text(self, mock_slack_client, mocker):
        event = _message_event(text="Hello world, nice weather today")
        await handle_message(
            event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"},
        )
        mock_slack_client.chat_postMessage.assert_not_called()

    @pytest.mark.anyio
    async def itShould_send_error_on_failure(self, mock_slack_client, mocker):
        mocker.patch.object(
            handlers_module, "detect_trigger",
            side_effect=RuntimeError("test failure"),
        )
        event = _message_event(text="drop fct_sales_pipeline")
        await handle_message(
            event, mock_slack_client, AsyncMock(), {"bot_user_id": "B777"},
        )
        error_calls = [
            c for c in mock_slack_client.chat_postMessage.call_args_list
            if ":warning:" in str(c.kwargs.get("text", ""))
        ]
        assert len(error_calls) >= 1


# ---- Start Cross-Team Review ----


class TestHandleStartCrossTeamReview:
    @pytest.mark.anyio
    async def itShould_ack_and_create_channel(
        self, mock_slack_client, _populate_cache, mocker,
    ):
        mock_slack_client.conversations_create.return_value = {
            "channel": {"id": "C_NEW", "name": "review-fct_sales_pipeline"},
        }
        mock_slack_client.conversations_invite = AsyncMock()
        mock_slack_client.pins_add = AsyncMock()
        mock_slack_client.chat_postMessage.return_value = {"ts": "pin_ts"}

        ack = AsyncMock()
        body = _action_body()
        await handle_start_cross_team_review(ack, body, mock_slack_client)

        ack.assert_called_once()
        mock_slack_client.conversations_create.assert_called_once()

    @pytest.mark.anyio
    async def itShould_fail_gracefully_on_channel_error(
        self, mock_slack_client, _populate_cache,
    ):
        from slack_sdk.errors import SlackApiError

        mock_slack_client.conversations_create.side_effect = SlackApiError(
            "err", {"ok": False},
        )
        ack = AsyncMock()
        body = _action_body()
        await handle_start_cross_team_review(ack, body, mock_slack_client)
        ack.assert_called_once()


# ---- Generate Migration Plan ----


class TestHandleGenerateMigrationPlan:
    @pytest.mark.anyio
    async def itShould_post_checklist_in_thread(
        self, mock_slack_client, sample_analysis,
    ):
        handlers_module._ANALYSIS_CACHE[("C123", "1234567890.123456")] = sample_analysis
        ack = AsyncMock()
        body = _action_body()
        await handle_generate_migration_plan(ack, body, mock_slack_client)

        ack.assert_called_once()
        call = mock_slack_client.chat_postMessage.call_args
        assert call.kwargs["channel"] == "C123"
        assert call.kwargs["blocks"] is not None

    @pytest.mark.anyio
    async def itShould_handle_missing_analysis(
        self, mock_slack_client,
    ):
        ack = AsyncMock()
        body = _action_body()
        await handle_generate_migration_plan(ack, body, mock_slack_client)

        warning_call = [
            c for c in mock_slack_client.chat_postMessage.call_args_list
            if ":warning:" in str(c.kwargs.get("text", ""))
        ]
        assert len(warning_call) >= 1


# ---- Mark as Outdated ----


class TestHandleMarkAsOutdated:
    @pytest.mark.anyio
    async def itShould_reply_to_stale_threads(
        self, mock_slack_client, sample_analysis, mocker,
    ):
        handlers_module._ANALYSIS_CACHE[("C123", "1234567890.123456")] = sample_analysis
        mocker.patch.object(
            handlers_module,
            "_get_message_permalink",
            return_value="https://slack.example.com/current",
        )
        ack = AsyncMock()
        body = _action_body()
        await handle_mark_as_outdated(ack, body, mock_slack_client)

        ack.assert_called_once()
        calls = mock_slack_client.chat_postMessage.call_args_list
        assert len(calls) >= 2

    @pytest.mark.anyio
    async def itShould_post_confirmation_even_with_no_stale(
        self, mock_slack_client, mocker,
    ):
        key = ("C123", "1234567890.123456")
        handlers_module._ANALYSIS_CACHE[key] = {
            **handlers_module._ANALYSIS_CACHE.get(key, {}),
            "stale_threads": [],
        }
        mocker.patch.object(
            handlers_module,
            "_get_message_permalink",
            return_value="https://slack.example.com/current",
        )
        ack = AsyncMock()
        body = _action_body()
        await handle_mark_as_outdated(ack, body, mock_slack_client)

        ack.assert_called_once()
        assert mock_slack_client.chat_postMessage.call_count >= 1


# ---- Annotate PR ----


class TestHandleAnnotatePr:
    @pytest.mark.anyio
    async def itShould_open_modal(self, mock_slack_client, sample_analysis):
        ack = AsyncMock()
        body = _action_body()
        await handle_annotate_pr(ack, body, mock_slack_client)

        ack.assert_called_once()
        mock_slack_client.views_open.assert_called_once()


class TestHandleAnnotatePrSubmission:
    @pytest.mark.anyio
    async def itShould_annotate_and_confirm(
        self, mock_slack_client, sample_analysis, mocker,
    ):
        handlers_module._ANALYSIS_CACHE[("C123", "1234567890.123456")] = sample_analysis
        mock_annotate = mocker.patch(
            "tracey.services.github_service.annotate_pr",
            return_value={
                "success": True,
                "pr_url": "https://github.com/o/r/pull/42",
            },
        )

        ack = AsyncMock()
        view = {
            "private_metadata": json.dumps({
                "model_name": "fct_sales_pipeline",
                "impact_summary": "## Test Summary",
                "repo": "test-org/test-repo",
                "channel_id": "C123",
                "message_ts": "1234567890.123456",
            }),
            "state": {
                "values": {
                    "pr_number_block": {
                        "pr_number_input": {"value": "42"},
                    },
                    "custom_summary_block": {
                        "custom_summary_input": {"value": ""},
                    },
                    "include_summary_block": {
                        "include_summary_checkbox": {
                            "selected_options": [
                                {"value": "include_full_summary"},
                            ],
                        },
                    },
                },
            },
        }
        await handle_annotate_pr_submission(ack, {"user": {"id": "U999"}}, mock_slack_client, view)

        ack.assert_called_once()
        mock_annotate.assert_called_once()
        confirm_calls = [
            c for c in mock_slack_client.chat_postMessage.call_args_list
            if "42" in str(c.kwargs.get("text", ""))
        ]
        assert len(confirm_calls) >= 1

    @pytest.mark.anyio
    async def itShould_reject_empty_pr_id(self, mock_slack_client, _populate_cache):
        ack = AsyncMock()
        view = {
            "private_metadata": json.dumps({
                "model_name": "fct_sales_pipeline",
                "impact_summary": "",
                "repo": "test-org/test-repo",
                "channel_id": "C123",
                "message_ts": "1234567890.123456",
            }),
            "state": {
                "values": {
                    "pr_number_block": {
                        "pr_number_input": {"value": ""},
                    },
                    "custom_summary_block": {
                        "custom_summary_input": {"value": ""},
                    },
                    "include_summary_block": {
                        "include_summary_checkbox": {
                            "selected_options": [],
                        },
                    },
                },
            },
        }
        await handle_annotate_pr_submission(ack, {"user": {"id": "U999"}}, mock_slack_client, view)
        ack_response = ack.call_args[0][0] if ack.call_args[0] else {}
        assert "errors" in ack_response
        assert "pr_number_block" in ack_response.get("errors", {})

    @pytest.mark.anyio
    async def itShould_handle_empty_private_metadata(self, mock_slack_client):
        ack = AsyncMock()
        view = {
            "private_metadata": "{}",
            "state": {"values": {}},
        }
        await handle_annotate_pr_submission(ack, {"user": {"id": "U999"}}, mock_slack_client, view)
        ack.assert_called_once()


# ---- Stale thread detection ----


class TestDetectStaleThreads:
    def itShould_flag_threads_before_last_change(self):
        from tracey.slack_agent.handlers import _detect_stale_threads

        rts_results = [
            {
                "message_ts": "1687531200.123456",
                "channel_id": "C456",
                "permalink": "https://slack.example.com/old",
            },
        ]
        last_change_ts = "2026-06-20T14:30:00"

        stale = _detect_stale_threads(rts_results, last_change_ts)
        assert len(stale) == 1
        assert stale[0]["channel"] == "C456"

    def itShould_return_empty_for_future_threads(self):
        from tracey.slack_agent.handlers import _detect_stale_threads

        rts_results = [
            {
                "message_ts": "1893456000.000000",
                "channel_id": "C456",
                "permalink": "https://slack.example.com/future",
            },
        ]
        stale = _detect_stale_threads(
            rts_results, "2026-06-20T14:30:00"
        )
        assert len(stale) == 0

    def itShould_deduplicate_by_channel(self):
        from tracey.slack_agent.handlers import _detect_stale_threads

        rts_results = [
            {
                "message_ts": "1687531200.123456",
                "channel_id": "C456",
                "permalink": "https://slack.example.com/a",
            },
            {
                "message_ts": "1687531300.123457",
                "channel_id": "C456",
                "permalink": "https://slack.example.com/b",
            },
        ]
        stale = _detect_stale_threads(
            rts_results, "2026-06-20T14:30:00"
        )
        assert len(stale) == 1


class TestRankExperts:
    def itShould_return_top_three_by_frequency(self):
        from tracey.slack_agent.handlers import _rank_experts

        rts_results = [
            {"author_user_id": "U001"},
            {"author_user_id": "U001"},
            {"author_user_id": "U002"},
            {"author_user_id": "U001"},
            {"author_user_id": "U003"},
            {"author_user_id": "U002"},
            {"author_user_id": "U004"},
        ]
        experts = _rank_experts(rts_results)
        assert len(experts) == 3
        assert experts[0] == "U001"
        assert experts[1] == "U002"
        assert experts[2] == "U003"

    def itShould_handle_empty_results(self):
        from tracey.slack_agent.handlers import _rank_experts

        experts = _rank_experts([])
        assert experts == []
