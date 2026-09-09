# Tracey — Makefile
# =============================================================================
# RAILWAY DEPLOYMENT (two services from one repo):
#   1. Each Railway service builds from the Dockerfile at the repo root.
#   2. Set the start command per service:
#        mcp           → start command: tracey
#        slack-agent   → start command: slack-agent
#   3. Health check path: /health
#
# LOCAL CONTAINERS:
#   make build   → build the image
#   make up      → run both services via compose
#   make down    → stop both services
# =============================================================================

CONTAINER ?= docker

.PHONY: setup seed-data dbt-run run-app run-slack-agent run-dev seed-slack test lint format build up down

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

run-dev:
	uv run tracey-dev

seed-slack:
	uv run python scripts/seed_slack.py

lint:
	uv run ruff check
	uv run ruff format --check

format:
	uv run ruff format

build:
	$(CONTAINER) build -t tracey .

up:
	$(CONTAINER) compose up

down:
	$(CONTAINER) compose down

test: lint
	uv run python -m pytest
