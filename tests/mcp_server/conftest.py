import importlib
import os

import pytest

import tracey.mcp_server.server as server_module


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure tests run with predictable environment variables."""
    monkeypatch.setenv("DUCKDB_PATH", "/tmp/test.duckdb")
    monkeypatch.setenv("MANIFEST_PATH", "/tmp/test_manifest.json")
    monkeypatch.setenv("DBT_PROJECT_DIR", "/tmp/test_compiled")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("GITHUB_REPO", "test-org/test-repo")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-signing-secret")
    monkeypatch.delenv("TRACEY_SKIP_SIGNATURE_CHECK", raising=False)
    importlib.reload(server_module)


@pytest.fixture
def mcp_server():
    """Return the FastMCP server with tools registered (after env reload)."""
    return server_module.mcp
