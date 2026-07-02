# Tracey — Makefile
# =============================================================================
# RAILWAY DEPLOYMENT (two services from one repo):
#   1. In Railway dashboard, create two services pointing at this repo:
#        mcp           → start command: uv run mcp-server
#        slack-agent   → start command: uv run slack-agent
#   2. Railpack auto-detects Python/UV via pyproject.toml.
# =============================================================================

.PHONY: setup seed-data dbt-run run-mcp run-slack-agent test

setup:
	uv sync --extra dev

seed-data:
	uv run python scripts/seed_sources.py
	uv run python scripts/seed_changelog.py
	uv run python scripts/seed_usage.py

dbt-run:
	cd dbt_project && uv run dbt deps && uv run dbt run && uv run dbt compile

run-mcp:
	uv run mcp-server

run-slack-agent:
	uv run slack-agent

test:
	uv run python -m pytest
