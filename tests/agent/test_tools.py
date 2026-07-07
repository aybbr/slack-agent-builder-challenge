"""Tests for agent/tools.py — tool definitions and delegation.

Service functions are mocked at the tools module level since imports
are resolved at module import time.
"""

from unittest.mock import AsyncMock

import pytest

from tracey.agent.context import tracey_deps_var
from tracey.agent.deps import TraceyDeps
from tracey.agent.tools import (
    add_reaction_tool,
    annotate_pr_tool,
    get_last_change_tool,
    get_migration_order_tool,
    get_usage_tool,
    search_slack_threads_tool,
)


class TestGetMigrationOrderTool:
    @pytest.mark.anyio
    async def itShould_return_json_result(self, mocker):
        mocker.patch(
            "tracey.agent.tools.get_migration_order",
            return_value={"asset_id": "fct_sales_pipeline", "migration_order": []},
        )
        result = await get_migration_order_tool.handler(
            {"model": "fct_sales_pipeline"},
        )
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

    @pytest.mark.anyio
    async def itShould_reject_empty_model(self):
        result = await get_migration_order_tool.handler({"model": ""})
        assert "error" in str(result["content"][0]["text"])


class TestGetUsageTool:
    @pytest.mark.anyio
    async def itShould_return_json_result(self, mocker):
        mocker.patch(
            "tracey.agent.tools.get_usage",
            return_value={"asset_id": "tst", "total_queries": 0},
        )
        result = await get_usage_tool.handler({"model": "fct_sales_pipeline"})
        assert "content" in result

    @pytest.mark.anyio
    async def itShould_reject_empty_model(self):
        result = await get_usage_tool.handler({"model": ""})
        assert "error" in str(result["content"][0]["text"])


class TestGetLastChangeTool:
    @pytest.mark.anyio
    async def itShould_return_json_result(self, mocker):
        mocker.patch(
            "tracey.agent.tools.get_last_change",
            return_value={"asset_id": "tst", "last_change": None},
        )
        result = await get_last_change_tool.handler({"model": "fct_sales_pipeline"})
        assert "content" in result

    @pytest.mark.anyio
    async def itShould_reject_empty_model(self):
        result = await get_last_change_tool.handler({"model": ""})
        assert "error" in str(result["content"][0]["text"])


class TestAnnotatePrTool:
    @pytest.mark.anyio
    async def itShould_return_json_result(self, mocker):
        mocker.patch(
            "tracey.agent.tools.annotate_pr",
            return_value={"success": True, "pr_url": "https://gh.com/1"},
        )
        result = await annotate_pr_tool.handler(
            {"pr_id": "42", "summary": "Impact summary"},
        )
        assert "content" in result

    @pytest.mark.anyio
    async def itShould_reject_empty_pr_id(self):
        result = await annotate_pr_tool.handler({"pr_id": "", "summary": "test"})
        assert "error" in str(result["content"][0]["text"])


class TestSearchSlackThreadsTool:
    @pytest.mark.anyio
    async def itShould_return_empty_list_without_deps(self):
        tracey_deps_var.set(None)
        result = await search_slack_threads_tool.handler(
            {"model": "fct_sales_pipeline"},
        )
        assert "content" in result

    @pytest.mark.anyio
    async def itShould_return_empty_list_without_user_token(self):
        deps = TraceyDeps(
            client=AsyncMock(),
            user_id="U123",
            channel_id="C123",
            thread_ts="ts.001",
            message_ts="ts.001",
            user_token=None,
        )
        tracey_deps_var.set(deps)
        result = await search_slack_threads_tool.handler(
            {"model": "fct_sales_pipeline"},
        )
        assert "content" in result
        tracey_deps_var.set(None)

    @pytest.mark.anyio
    async def itShould_reject_empty_model(self):
        result = await search_slack_threads_tool.handler({"model": ""})
        assert "error" in str(result["content"][0]["text"])


class TestAddReactionTool:
    @pytest.mark.anyio
    async def itShould_return_error_without_deps(self):
        tracey_deps_var.set(None)
        result = await add_reaction_tool.handler({"emoji_name": "eyes"})
        assert "error" in str(result["content"][0]["text"])
