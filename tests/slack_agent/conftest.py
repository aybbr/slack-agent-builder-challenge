import json
import os
from unittest.mock import AsyncMock

import pytest

import tracey.slack_agent.handlers as handlers_module


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure tests run with predictable environment variables."""
    monkeypatch.setattr(
        handlers_module, "_MANIFEST_PATH", "/tmp/test_manifest.json",
    )
    monkeypatch.setattr(
        handlers_module, "_DUCKDB_PATH", "/tmp/test.duckdb",
    )
    monkeypatch.setattr(
        handlers_module, "_DBT_PROJECT_DIR", "/tmp/test_compiled",
    )
    monkeypatch.setattr(
        handlers_module, "_GITHUB_TOKEN", "ghp_test_token",
    )
    monkeypatch.setattr(
        handlers_module, "_GITHUB_REPO", "test-org/test-repo",
    )
    monkeypatch.setattr(
        handlers_module, "_SLACK_USER_TOKEN", "xoxp-test-user-token",
    )
    monkeypatch.setattr(
        handlers_module, "_TARGET_CHANNEL_IDS", frozenset(),
    )
    handlers_module.PROCESSED_MESSAGES.clear()
    handlers_module._ANALYSIS_CACHE.clear()


@pytest.fixture
def mock_slack_client():
    """Return an AsyncMock simulating slack_sdk.web.async_client.AsyncWebClient."""
    client = AsyncMock()
    client.reactions_add = AsyncMock()
    client.chat_postMessage = AsyncMock()
    client.chat_getPermalink = AsyncMock()
    client.search_messages = AsyncMock()
    client.conversations_create = AsyncMock()
    client.conversations_invite = AsyncMock()
    client.pins_add = AsyncMock()
    client.views_open = AsyncMock()
    return client


@pytest.fixture
def manifest_path(tmp_path):
    """Create a minimal dbt manifest JSON for prefilter tests."""
    manifest = {
        "nodes": {
            "model.tracey_demo.stg_salesforce__opportunity": {
                "name": "stg_salesforce__opportunity",
                "resource_type": "model",
            },
            "model.tracey_demo.stg_finance__revenue": {
                "name": "stg_finance__revenue",
                "resource_type": "model",
            },
            "model.tracey_demo.fct_sales_pipeline": {
                "name": "fct_sales_pipeline",
                "resource_type": "model",
            },
            "model.tracey_demo.fct_revenue_recognition": {
                "name": "fct_revenue_recognition",
                "resource_type": "model",
            },
            "model.tracey_demo.rpt_commissions": {
                "name": "rpt_commissions",
                "resource_type": "model",
            },
            "test.tracey_demo.not_null_test": {
                "name": "not_null_test",
                "resource_type": "test",
            },
        }
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return str(path)


@pytest.fixture
def sample_analysis():
    """Return a complete analysis dict for card building and handler tests."""
    return {
        "model": "fct_sales_pipeline",
        "intent": "deprecate",
        "column": "lead_score",
        "channel_id": "C123",
        "message_ts": "1234567890.123456",
        "lineage": {
            "asset_id": "fct_sales_pipeline",
            "domain": "sales",
            "upstream": [
                {"id": "stg_salesforce__opportunity", "domain": "staging"},
            ],
            "downstream": [
                {
                    "id": "fct_revenue_recognition",
                    "domain": "finance",
                    "cross_domain": True,
                },
                {
                    "id": "rpt_commissions",
                    "domain": "sales",
                    "cross_domain": False,
                },
            ],
        },
        "migration_order": {
            "asset_id": "fct_sales_pipeline",
            "domain": "sales",
            "migration_order": [
                {
                    "id": "fct_sales_pipeline",
                    "domain": "sales",
                    "order": 1,
                    "is_source": True,
                    "cross_domain": False,
                },
                {
                    "id": "fct_revenue_recognition",
                    "domain": "finance",
                    "order": 2,
                    "is_source": False,
                    "cross_domain": True,
                },
                {
                    "id": "rpt_commissions",
                    "domain": "sales",
                    "order": 3,
                    "is_source": False,
                    "cross_domain": False,
                },
            ],
        },
        "column_lineage": {
            "asset_id": "fct_sales_pipeline",
            "column_name": "lead_score",
            "downstream_usages": [
                {
                    "model": "fct_revenue_recognition",
                    "column": "lead_score_weighted",
                    "usage_type": "expression",
                    "confidence": "high",
                },
            ],
            "warnings": [],
        },
        "usage": {
            "asset_id": "fct_sales_pipeline",
            "by_domain": [
                {"domain": "sales", "queries": 450, "dashboards": 3},
                {"domain": "finance", "queries": 320, "dashboards": 2},
            ],
            "total_queries": 770,
            "total_dashboards": 5,
        },
        "last_change": {
            "asset_id": "fct_sales_pipeline",
            "last_change": {
                "changed_at": "2026-06-20T14:30:00",
                "change_type": "refactor",
                "changed_by": "sales_engineer",
                "summary": "Optimized pipeline joins",
            },
        },
        "tests": {
            "asset_id": "fct_sales_pipeline",
            "tests": [
                {
                    "name": "not_null_fct_sales_pipeline_opportunity_id",
                    "column": "opportunity_id",
                    "type": "not_null",
                    "severity": "error",
                },
            ],
            "referential_tests": [
                {
                    "name": "relationships_fct_revenue_recognition_opportunity_id",
                    "column": "opportunity_id",
                    "type": "relationships",
                    "severity": "error",
                    "owner": "fct_revenue_recognition",
                },
            ],
        },
        "stale_threads": [
            {
                "ts": "1687531200.123456",
                "channel": "C456",
                "permalink": "https://slack.example.com/thread/1",
            },
        ],
        "experts": ["U001", "U002", "U003"],
    }
