# Tracey — Makefile
# =============================================================================
# RAILWAY DEPLOYMENT (two services from one repo):
#   1. In Railway dashboard, create two services pointing at this repo:
#        mcp           → start command: uv run mcp-server
#        slack-agent   → start command: uv run slack-agent
#   2. Railpack auto-detects Python/UV via pyproject.toml.
# =============================================================================

.PHONY: setup seed-data dbt-run run-app run-slack-agent test lint format

setup:
	uv sync --extra dev

seed-data:
	uv run python scripts/seed_sources.py
	uv run python scripts/seed_changelog.py
	uv run python scripts/seed_usage.py

dbt-run:
	cd dbt_project && uv run dbt deps && uv run dbt run && uv run dbt test && uv run dbt compile

run-app:
	uv run tracey

run-slack-agent:
	uv run slack-agent

lint:
	uv run ruff check
	uv run ruff format --check

format:
	uv run ruff format

test: lint
	uv run python -m pytest
