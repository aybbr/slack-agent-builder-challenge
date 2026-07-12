import asyncio

import pytest
from starlette.testclient import TestClient

from tests.mcp_server.conftest import server_module


class TestToolRegistration:
    """Verify that all Tracey-specific MCP tools are registered correctly."""

    EXPECTED_TOOLS = {
        "get_migration_order",
        "get_usage",
        "get_last_change",
        "annotate_pr",
        "close_pr",
    }

    _NON_READ_ONLY = {"annotate_pr", "close_pr"}

    @pytest.fixture
    def component_names(self, mcp_server):
        provider = mcp_server._local_provider
        return set(provider._components.keys())

    def itShould_register_five_tools(self, mcp_server):
        provider = mcp_server._local_provider
        tool_components = {k for k in provider._components if k.startswith("tool:")}
        assert len(tool_components) == 5

    def itShould_register_all_expected_tool_names(self, mcp_server):
        provider = mcp_server._local_provider
        tool_names = {k.split("tool:")[1].split("@")[0] for k in provider._components if k.startswith("tool:")}
        assert tool_names == self.EXPECTED_TOOLS

    def itShould_have_read_only_annotations_on_read_tools(self, mcp_server):
        provider = mcp_server._local_provider
        for key, tool in provider._components.items():
            if not key.startswith("tool:"):
                continue
            tool_name = key.split("tool:")[1].split("@")[0]
            if tool_name in self._NON_READ_ONLY:
                assert tool.annotations.readOnlyHint is False, f"{tool_name} should not be read-only"
            else:
                assert tool.annotations.readOnlyHint is True, f"{tool_name} should be read-only"


class TestHealthEndpoint:
    """Verify the health check endpoint."""

    def itShould_return_200_and_ok_status(self):
        from tracey.app import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSlackSignatureMiddleware:
    """Verify Slack signature verification on the MCP endpoint."""

    def itShould_reject_unsigned_request_with_401(self):
        from tracey.app import app

        client = TestClient(app, raise_server_exceptions=False)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
        response = client.post("/mcp", json=payload)
        assert response.status_code == 401
        body = response.json()
        assert body["jsonrpc"] == "2.0"
        assert "error" in body

    def itShould_allow_signed_request_past_middleware(self):
        """Verify signature verification passes for valid signatures.

        This test verifies the middleware layer only (not the MCP app),
        because the FastMCP HTTP app requires a proper async server context
        that is not available with TestClient. The MCP endpoint integration
        is tested in Stream 6 end-to-end tests.
        """
        from tracey.mcp_server.server import SlackSignatureMiddleware

        middleware = SlackSignatureMiddleware(SimpleASGIApp())
        headers = _build_slack_headers("test-signing-secret", "test body")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        }

        received = []

        async def mock_receive():
            if not received:
                received.append(True)
                return {
                    "type": "http.request",
                    "body": b"test body",
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        sent = []

        async def mock_send(message):
            sent.append(message)

        asyncio.run(middleware(scope, mock_receive, mock_send))

        body_sent = {}
        for msg in sent:
            if msg.get("type") == "http.response.body":
                body_sent["body"] = body_sent.get("body", b"") + msg.get("body", b"")

        assert body_sent.get("body") == b"test body", f"Expected body 'test body', got {body_sent.get('body')}"


class TestAnnotatePRTool:
    """Verify the annotate_pr tool validates input and delegates."""

    def itShould_call_github_service(self, mcp_server, mocker):
        mock_annotate = mocker.patch.object(
            server_module,
            "annotate_pr",
            return_value={"success": True, "pr_url": "https://github.com/t"},
        )
        tool = _find_tool(mcp_server, "annotate_pr")
        result = tool.fn("42", "## Impact Analysis\n\nTest summary")
        mock_annotate.assert_called_once_with(
            "42",
            "## Impact Analysis\n\nTest summary",
            "test-org/test-repo",
            "ghp_test_token",
        )
        assert result["success"] is True

    def itShould_reject_empty_pr_id(self, mcp_server, mocker):
        mocker.patch.object(server_module, "annotate_pr")
        tool = _find_tool(mcp_server, "annotate_pr")
        result = tool.fn("", "summary")
        assert "error" in result

    def itShould_reject_empty_summary(self, mcp_server, mocker):
        mocker.patch.object(server_module, "annotate_pr")
        tool = _find_tool(mcp_server, "annotate_pr")
        result = tool.fn("42", "")
        assert "error" in result

    def itShould_reject_non_numeric_pr_id(self, mcp_server, mocker):
        mocker.patch.object(server_module, "annotate_pr")
        tool = _find_tool(mcp_server, "annotate_pr")
        result = tool.fn("abc", "summary")
        assert "error" in result


class TestClosePRTool:
    """Verify the close_pr tool validates input and delegates."""

    def itShould_call_github_service(self, mcp_server, mocker):
        mock_close = mocker.patch.object(
            server_module,
            "close_pr",
            return_value={"success": True, "pr_url": "https://github.com/t", "state": "closed"},
        )
        tool = _find_tool(mcp_server, "close_pr")
        result = tool.fn("42", "Realigning with data owners first")
        mock_close.assert_called_once_with(
            "42",
            "test-org/test-repo",
            "ghp_test_token",
            comment="Realigning with data owners first",
        )
        assert result["success"] is True

    def itShould_close_without_comment(self, mcp_server, mocker):
        mock_close = mocker.patch.object(
            server_module,
            "close_pr",
            return_value={"success": True, "pr_url": "https://github.com/t", "state": "closed"},
        )
        tool = _find_tool(mcp_server, "close_pr")
        result = tool.fn("42")
        assert mock_close.call_args.kwargs["comment"] is None
        assert result["success"] is True

    def itShould_reject_empty_pr_id(self, mcp_server, mocker):
        mocker.patch.object(server_module, "close_pr")
        tool = _find_tool(mcp_server, "close_pr")
        result = tool.fn("")
        assert "error" in result

    def itShould_reject_non_numeric_pr_id(self, mcp_server, mocker):
        mocker.patch.object(server_module, "close_pr")
        tool = _find_tool(mcp_server, "close_pr")
        result = tool.fn("abc")
        assert "error" in result


class TestMigrationOrderTool:
    """Verify the get_migration_order tool delegates correctly."""

    def itShould_call_migration_order_service(self, mcp_server, mocker):
        mock_order = mocker.patch.object(
            server_module,
            "get_migration_order",
            return_value={"asset_id": "tst", "migration_order": []},
        )
        tool = _find_tool(mcp_server, "get_migration_order")
        result = tool.fn("fct_sales_pipeline")
        mock_order.assert_called_once_with("fct_sales_pipeline", "/tmp/test_manifest.json")
        assert result["asset_id"] == "tst"


class TestUsageTool:
    """Verify the get_usage tool delegates correctly."""

    def itShould_call_usage_service(self, mcp_server, mocker):
        mock_usage = mocker.patch.object(
            server_module,
            "get_usage",
            return_value={"asset_id": "tst", "total_queries": 0, "total_dashboards": 0},
        )
        tool = _find_tool(mcp_server, "get_usage")
        result = tool.fn("fct_sales_pipeline")
        mock_usage.assert_called_once_with("fct_sales_pipeline", "/tmp/test.duckdb")
        assert result["asset_id"] == "tst"


class TestLastChangeTool:
    """Verify the get_last_change tool delegates correctly."""

    def itShould_call_changelog_service(self, mcp_server, mocker):
        mock_change = mocker.patch.object(
            server_module,
            "get_last_change",
            return_value={"asset_id": "tst", "last_change": None},
        )
        tool = _find_tool(mcp_server, "get_last_change")
        result = tool.fn("fct_sales_pipeline")
        mock_change.assert_called_once_with("fct_sales_pipeline", "/tmp/test.duckdb")
        assert result["asset_id"] == "tst"


# --- helpers ---


class SimpleASGIApp:
    """A minimal ASGI app that echoes the request body as the response body.

    Used to test middleware isolation without a real MCP server.
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body if body else b"forwarded",
                "more_body": False,
            }
        )


def _find_tool(mcp_server, tool_name: str):
    """Find a registered tool by name in the FastMCP provider."""
    provider = mcp_server._local_provider
    for key, tool in provider._components.items():
        if key.startswith(f"tool:{tool_name}"):
            return tool
    raise KeyError(f"Tool '{tool_name}' not found in registered tools")


def _build_slack_headers(secret: str, body: str) -> dict:
    """Build valid X-Slack-Signature and X-Slack-Request-Timestamp headers."""
    import hashlib
    import hmac
    import time

    timestamp = str(int(time.time()))
    sig_basestring = f"v0:{timestamp}:{body}"
    signature = (
        "v0="
        + hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    return {
        "Content-Type": "application/json",
        "X-Slack-Signature": signature,
        "X-Slack-Request-Timestamp": timestamp,
    }
