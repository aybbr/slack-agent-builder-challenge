"""Tests for agent/mcp_config.py — MCP server configuration builder."""

from unittest.mock import MagicMock

from tracey.agent.deps import TraceyDeps
from tracey.agent.mcp_config import build_mcp_servers


def _make_deps(*, user_token: str | None = None) -> TraceyDeps:
    return TraceyDeps(
        client=MagicMock(),
        user_id="U123",
        channel_id="C123",
        thread_ts="1234.5678",
        message_ts="1234.5678",
        user_token=user_token,
    )


class TestBuildMcpServers:
    def itShould_always_include_tracey_and_dbt_and_mermaid(self):
        deps = _make_deps()
        servers, tools = build_mcp_servers(deps, object(), "/tmp/dbt")

        assert "tracey-tools" in servers
        assert "dbt" in servers
        assert "mermaid" in servers

    def itShould_not_include_slack_mcp_without_user_token(self):
        deps = _make_deps(user_token=None)
        servers, tools = build_mcp_servers(deps, object(), "/tmp/dbt")

        assert "slack-mcp" not in servers

    def itShould_include_slack_mcp_with_user_token(self):
        deps = _make_deps(user_token="xoxp-token")
        servers, tools = build_mcp_servers(deps, object(), "/tmp/dbt")

        assert "slack-mcp" in servers
        assert servers["slack-mcp"]["url"] == "https://mcp.slack.com/mcp"

    def itShould_include_tracey_tool_names(self):
        deps = _make_deps()
        _, tools = build_mcp_servers(deps, object(), "/tmp/dbt")

        tracey_tools = [t for t in tools if t.startswith("mcp__tracey-tools__")]
        assert any("render_diagram_to_slack" in t for t in tracey_tools)
        assert any("get_migration_order" in t for t in tracey_tools)
        assert any("add_reaction" in t for t in tracey_tools)

    def itShould_include_external_namespaces(self):
        deps = _make_deps()
        _, tools = build_mcp_servers(deps, object(), "/tmp/dbt")

        assert "mcp__dbt__*" in tools
        assert "mcp__mermaid__*" in tools

    def itShould_add_slack_namespace_when_authenticated(self):
        deps = _make_deps(user_token="xoxp-token")
        _, tools = build_mcp_servers(deps, object(), "/tmp/dbt")

        assert "mcp__slack-mcp__*" in tools

    def itShould_handle_none_deps(self):
        servers, tools = build_mcp_servers(None, object(), "/tmp/dbt")

        assert "slack-mcp" not in servers
        assert "mcp__slack-mcp__*" not in tools
        assert "tracey-tools" in servers
        assert "mermaid" in servers

    def itShould_set_dbt_project_dir(self):
        servers, _ = build_mcp_servers(None, object(), "/custom/dbt/path")

        assert servers["dbt"]["env"]["DBT_PROJECT_DIR"] == "/custom/dbt/path"

    def itShould_set_mermaid_url_to_http(self):
        servers, _ = build_mcp_servers(None, object(), "/tmp/dbt")

        assert servers["mermaid"]["type"] == "http"
        assert servers["mermaid"]["url"] == "https://mcp.mermaid.ai/mcp"
