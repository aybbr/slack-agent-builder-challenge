# Tracey

Cross-domain data change intelligence agent for Slack.

## Quick Start

```bash
make setup        # install dependencies
make seed-data    # populate DuckDB
make dbt-run      # compile dbt models
make run-mcp      # start MCP server
make run-slack-agent  # start Slack agent (Socket Mode)
make test         # run tests
```

## Railway Deployment

This is a monorepo with two services. Railpack auto-detects Python/UV.

1. Create two services in the Railway dashboard, both pointed at this repo.
2. Configure each service's start command:

   **mcp service:**
   ```
   uv run mcp-server
   ```

   **slack-agent service:**
   ```
   uv run slack-agent
   ```
