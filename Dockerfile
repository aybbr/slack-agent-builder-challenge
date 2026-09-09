FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY . .

RUN uv sync --no-dev

EXPOSE 8000

# Default entrypoint is the MCP server; the Slack agent service overrides the
# start command to `slack-agent`. The console scripts are installed into
# /app/.venv/bin (on PATH) by `uv sync`.
CMD ["tracey"]
