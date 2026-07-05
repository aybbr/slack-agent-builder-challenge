# Tracey — Implementation Roadmap

## Architecture Recap

**Single deployable service** (shared Starlette app) in a monorepo:

```
slack-agent-builder-challenge/
├── src/tracey/                 # Python package
│   ├── app.py                      # Starlette entrypoint (composes MCP + Bolt)
│   ├── services/                   # Pure domain logic (no Slack/MCP deps)
│   │   ├── lineage_service.py
│   │   ├── usage_service.py
│   │   ├── github_service.py
│   │   ├── test_service.py
│   │   └── changelog_service.py
│   ├── mcp_server/                 # MCP tools + signature middleware
│   │   └── server.py
│   ├── slack_agent/                # Bolt agent (Stream 4)
│   │   └── app.py
│   └── utils/
│       └── errors.py               # Shared error_response helper
├── scripts/                   # Setup & seed scripts
│   ├── seed_sources.py
│   ├── seed_usage.py
│   └── seed_changelog.py
├── dbt_project/               # dbt models, profiles, manifest (committed)
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   └── target/                # manifest.json, compiled SQL (committed for Railway)
├── tests/                     # Pytest test suite
├── data/                      # demo.duckdb (committed for Railway)
├── pyproject.toml
├── uv.lock
├── Makefile
├── railway.json
├── .env.example               # env var template
├── AGENTS.md                  # AI agent rules
├── ROADMAP.md                 # this file
└── .gitignore
```

Key decisions:
- **fastmcp** (community) for MCP tool definitions — protocol-compatible, cleaner composability.
- **slack_identity_auth** for Slackbot MCP Client — identity context without OAuth burden.
- **Single Starlette app** — MCP tools and Bolt agent share one uvicorn process, calling `services/` directly (no network hop).
- **SlackSignatureMiddleware** — HMAC-SHA256 verification on every `/mcp` request (required by Slack).
- **Railpack** auto-detects Python/UV on Railway.
- **Streamable HTTP** transport for MCP (JSON-RPC 2.0).

---

## Streams Overview

| Stream | Name | Status | Dependencies | Key Deliverables |
|--------|------|--------|--------------|------------------|
| 0 | Project Scaffold & Tooling | ✅ Done | None | pyproject.toml, UV config, directory tree, Makefile, Railway config |
| 1 | Data Layer (dbt + DuckDB) | ✅ Done | Stream 0 | dbt project, seed scripts, compiled manifest, demo.duckdb with changelog & usage |
| 2 | Domain Library (services) | ✅ Done | Stream 1 | services/*.py with 7 public functions, 38 unit tests |
| 3 | MCP Adapter | ✅ Done | Stream 2 | 7 MCP tools, SlackSignatureMiddleware, health endpoint, Starlette entrypoint |
| 4 | Slack Agent | ⬜ Todo | Stream 2 & 3 (shared app) | Bolt event handlers, trigger detection, Block Kit, interactivity |
| 5 | Slack Workspace Seeding | ⬜ Todo | None (manual) | Realistic channels, threads, and users |
| 6 | Integration & Demo Script | ⬜ Todo | All previous | End-to-end test, runbook, demo video script |

### Progress

```
Stream 0 ████████████ Done
Stream 1 ████████████ Done
Stream 2 ████████████ Done
Stream 3 ████████████ Done
Stream 4 ░░░░░░░░░░░░ Todo
Stream 5 ░░░░░░░░░░░░ Todo
Stream 6 ░░░░░░░░░░░░ Todo
```

### Dependency Graph

```
Stream 0 ✅ → Stream 1 ✅ → Stream 2 ✅ → Stream 3 ✅ (MCP tools + entrypoint)
                                        → Stream 4 ⬜ (Bolt routes, extends same app)
Stream 5 ⬜ (independent)
Stream 6 ⬜ (after 1-5)
```

---

## Stream 0 – Project Scaffold & Tooling ✅

**Goal:** Create the monorepo structure with UV, configure Railway, and set up a Makefile.

**Tasks:**
1. ~~`uv init --package tracey`~~ Done
2. ~~Organise `src/tracey/` to match final tree (sub-directories, `__init__.py` files)~~ Done
3. ~~Write `pyproject.toml` with dependencies, scripts, and build config~~ Done
4. ~~Create `.gitignore`~~ Done
5. ~~Create `railway.json` with Railpack builder~~ Done
6. ~~Create `Makefile` (setup, seed-data, dbt-run, run-mcp, run-slack-agent, test)~~ Done
7. ~~Commit~~ Done

**Additional items added during implementation:**
- `AGENTS.md` — project rules for AI coding agents (naming convention: "slack agent" not "bot")
- `ROADMAP.md` — this file
- `tests/` with `conftest.py` — pytest setup
- `.env.example` — env var template
- `[tool.pytest.ini_options]` in pyproject.toml

---

## Stream 1 – Data Layer (dbt + DuckDB) ✅

**Goal:** Create a realistic dbt project, compile the manifest, seed DuckDB with source data, changelog, and usage stats.

**Steps:**

1. ~~Create `dbt_project/dbt_project.yml`~~ Done — profile: tracey_demo, models tagged with domain:sales or domain:finance
2. ~~Create `dbt_project/profiles.yml`~~ Done — DuckDB at `../data/demo.duckdb`
3. ~~Write models~~ Done:
   - ~~`models/staging/stg_salesforce__opportunity.sql`~~
   - ~~`models/staging/stg_finance__revenue.sql`~~
   - ~~`models/staging/stg_customer.sql`~~
   - ~~`models/marts/dim_customer.sql`~~
   - ~~`models/marts/fct_sales_pipeline.sql` (domain:sales, includes lead_score)~~
   - ~~`models/marts/fct_revenue_recognition.sql` (domain:finance, uses lead_score * 0.3)~~
   - ~~`models/marts/rpt_commissions.sql` (domain:sales, uses lead_score_weighted)~~
4. ~~Add tests in `schema.yml`~~ Done — not_null, unique, accepted_values, relationships — 5/5 PASS
5. ~~Create seed scripts~~ Done:
   - ~~`scripts/seed_sources.py` — 41 rows across 3 raw tables~~
   - ~~`scripts/seed_changelog.py` — 3 strategic timestamps~~
   - ~~`scripts/seed_usage.py` — 8 rows across 4 assets × 2 domains~~
6. ~~Run dbt~~ Done — `dbt deps && dbt run && dbt test && dbt compile` all green, 0 warnings

**Key changelog timestamps (for stale detection):**
| Asset | Date | Type | Purpose |
|-------|------|------|---------|
| fct_sales_pipeline | 2026-05-15 | column_drop | After April thread → stale |
| fct_sales_pipeline | 2026-06-20 | refactor | Before June 25 thread |
| fct_revenue_recognition | 2026-04-01 | column_add | Earliest context |

---

## Stream 2 – Domain Library (services/) ✅

**Goal:** Implement all pure business logic functions. No Slack imports. Unit-testable.

**Implemented modules:**

### _manifest_helpers.py (private)
- `_load_manifest`, `_resolve_asset_id`, `_get_node`, `_get_upstream_models`, `_get_downstream_models`, `_topological_sort` — shared graph traversal used by lineage and test services

### lineage_service.py
- `get_lineage(asset_id, manifest_path) → dict` — upstream/downstream from manifest, cross-domain detection
- `get_migration_order(asset_id, manifest_path) → dict` — topological sort of all descendants with contiguous ordering
- `get_column_lineage(asset_id, column_name, manifest_path, compiled_dir) → dict` — SQLGlot AST-based column tracing through compiled SQL, returns `warnings` for missing files and `confidence` (`high`/`low`) per usage

### changelog_service.py
- `get_last_change(asset_id, db_path) → dict` — nested `last_change` shape with ISO-8601 timestamps

### usage_service.py
- `get_usage(asset_id, db_path) → dict` — aggregate usage_stats by domain with totals

### test_service.py
- `get_tests(asset_id, manifest_path) → dict` — uses manifest metadata as primary source; splits owned `tests` from `referential_tests` (e.g. relationships tests owned by another model)

### github_service.py
- `annotate_pr(pr_id, summary, repo_name, token) → dict` — post PR comment via PyGithub

### utils/errors.py
- `error_response(asset_id, message, **extra) → dict` — standardized `{"asset_id": ..., "error": ...}` shape used by all services

**Tests:** 38 tests across 5 test files using `itShould_*` / `itShouldnt_*` naming convention. All pass against synthetic fixtures. Verified against real dbt manifest and DuckDB.

**Review fixes applied after initial implementation:**
- Changelog response normalized to nested `last_change` shape
- `duckdb.Error` caught specifically instead of bare `Exception`
- Migration order uses separate counter for contiguous numbering
- Test attributes sourced from manifest metadata, not unique_id parsing
- Column lineage returns `warnings` list for missing compiled files
- Renamed `get_last_schema_change` → `get_last_change` per roadmap spec
- Makefile `dbt-run` includes `dbt test`

**Hardening applied in PR #2 (MCP adapter):**
- Standardized error responses via `utils/errors.py` across all services
- `get_tests` filters on `attached_node`; relationships tests reported in `referential_tests` with `owner`
- Severity normalized to lowercase (`"error"` not `"ERROR"`)
- Column lineage adds `confidence` (`high` / `low`) for qualified vs unqualified column refs
- Schema-qualified dbt compiled SQL alias detection (e.g. `"demo"."main_main"."fct_sales_pipeline" sp`)
- SQLGlot parse errors surfaced in `warnings` instead of silently swallowed
- Seed scripts use `with duckdb.connect(...)` context managers

---

## Stream 3 – MCP Adapter ✅

**Goal:** Wrap the domain library into a FastMCP server, expose tools via Streamable HTTP with Slack signature verification, and create the shared Starlette entrypoint for the entire application.

**Architecture decisions (anchored):**
- **fastmcp**: Use `fastmcp` (community `FastMCP`) — protocol-compatible with Slackbot MCP Client, `http_app()` returns a composable `StarletteWithLifespan`.
- **Auth**: `slack_identity_auth` — every `/mcp` request verified via `SlackSignatureMiddleware` (HMAC-SHA256). Slack injects `_meta.slack` with user/team identity. No user OAuth needed.
- **Transport**: `stateless_http=True`, `json_response=True` — Streamable HTTP at `/mcp`.
- **Dev skip**: `TRACEY_SKIP_SIGNATURE_CHECK=1` bypasses signature verification for local development.

**Delivered (PR #2):**

1. ~~`src/tracey/mcp_server/server.py` — 7 MCP tools + `SlackSignatureMiddleware` class~~ Done
2. ~~`src/tracey/app.py` — Starlette entrypoint: `GET /health`, `POST /mcp`, uvicorn on `0.0.0.0:$PORT`~~ Done
3. ~~`railway.json` — health check at `/health`, restart policy~~ Done
4. ~~`pyproject.toml` — `tracey` console script pointing to `tracey.app:main`~~ Done
5. ~~`tests/mcp_server/` — 19 tests (tool registration, middleware, health endpoint, input validation, delegation)~~ Done

**Files:**
- `src/tracey/mcp_server/server.py` — 7 MCP tools + `SlackSignatureMiddleware` class
- `src/tracey/app.py` — Starlette entrypoint: `GET /health`, `POST /mcp`, uvicorn on `0.0.0.0:$PORT`
- `railway.json` — health check at `/health`, restart policy
- `tests/mcp_server/` — 19 tests (tool registration, middleware, health endpoint, input validation)

**Tools exposed:**

| Tool | Parameters | Service called | Env vars used |
|------|-----------|---------------|---------------|
| `get_lineage` | `asset_id: str` | `lineage_service.get_lineage` | `MANIFEST_PATH` |
| `get_migration_order` | `asset_id: str` | `lineage_service.get_migration_order` | `MANIFEST_PATH` |
| `get_column_lineage` | `asset_id: str`, `column_name: str` | `lineage_service.get_column_lineage` | `MANIFEST_PATH`, `DBT_PROJECT_DIR` |
| `get_usage` | `asset_id: str` | `usage_service.get_usage` | `DUCKDB_PATH` |
| `get_last_change` | `asset_id: str` | `changelog_service.get_last_change` | `DUCKDB_PATH` |
| `get_tests` | `asset_id: str` | `test_service.get_tests` | `MANIFEST_PATH` |
| `annotate_pr` | `pr_id: str`, `summary: str` | `github_service.annotate_pr` | `GITHUB_TOKEN`, `GITHUB_REPO` |

Each tool is a thin wrapper: validate input → call service → return dict. Read-only tools annotated with `ToolAnnotations(readOnlyHint=True)`; `annotate_pr` is `readOnlyHint=False`. Docstrings serve as LLM-facing tool descriptions.

**Middleware:**
- `SlackSignatureMiddleware` — ASGI middleware wrapping the MCP app. Verifies `X-Slack-Signature` and `X-Slack-Request-Timestamp` on every `/mcp` request. Returns JSON-RPC 401 on invalid signature. Skippable via `TRACEY_SKIP_SIGNATURE_CHECK`.
- Health check — `GET /health` returns `{"status": "ok"}` (200). No auth required on this route.

**Railway deployment:**
- Railpack auto-detects Python/UV
- Single service with `healthcheckPath: "/health"`
- Data files (`data/demo.duckdb`, `dbt_project/target/`) committed to git so they're present at runtime
- Restart policy: `ON_FAILURE`, max 3 retries

**Tests:** 57 total (38 service + 19 MCP). Run via `make test`.

> **Future improvement (Stream 4):** Add `@lru_cache` to `_load_manifest` in `_manifest_helpers.py` to avoid re-parsing the manifest on every tool call when multiple tools are invoked in parallel (Stream 4 fires ~5 calls per trigger). Not needed for initial demo.

---

## Stream 4 – Slack Agent

**Goal:** Build the interactive Slack agent that triggers on change-intent messages, calls services directly (shared library, separate process), presents a Block Kit card, and handles button actions via modals and rich threaded replies.

**Runs as a standalone Starlette service.** Exposes `GET /health`, `POST /slack/events`, `POST /slack/interactivity`. Shares `services/` and data assets with the MCP service but runs in its own process.

**Detailed requirements:**

1. Bolt app setup as standalone service (no Socket Mode — HTTP events). Listen for messages in `#sales-data`, `#finance-data`, `#data-ops`.

2. Trigger detection: parse text for model names + change-intent keywords (drop, remove, deprecate, rename, change, refactor).

3. Analysis: parallel calls to services/ functions for lineage, usage, column lineage, last change, tests. Slack MCP Server for RTS search of past threads.

4. Expert & stale detection: rank top 3 experts by replies. Compare thread timestamps with `last_change_ts`. Use `slack_identity_auth` `_meta.slack` for identity resolution.

5. Block Kit card:
   - Header with warning
   - Structural impact (cross-domain downstream, column-level lineage)
   - Usage statistics per domain
   - Migration order preview
   - Social impact (experts with @mentions, stale threads)
   - Action buttons: Start Cross-Team Review, Generate Migration Plan, Mark as Outdated, Annotate PR

6. Interactive button handlers — **all replies use Block Kit blocks**, never plain text:
   - Start Cross-Team Review: create channel, invite experts, post Block Kit summary in original thread (header + context + expert list), pin summary in new channel
   - Generate Migration Plan: post checklist Block Kit blocks (emoji status per step) as threaded reply
   - Mark as Outdated: post Block Kit outdated notice (section + context block) as threaded reply within each stale thread; confirm in current thread
   - Annotate PR: modal (`views.open` + `view_submission`) collects PR number + optional summary; `private_metadata` carries context; posts Block Kit confirmation in original thread with PR link

---

## Stream 5 – Slack Workspace Seeding

**Goal:** Populate the Slack sandbox with realistic threads.

**Tasks:**
1. Create channels: `#sales-data`, `#finance-data`, `#data-ops`
2. Create test users: `sales_engineer`, `fpanda_lead`, `data_platform`
3. Post threads:
   - In `#finance-data` (2026-04-10): "Quick reminder: the revenue report depends on fct_sales_pipeline. Don't change lead_score without notifying Finance."
   - In `#sales-data` (2026-06-25): "I'm seeing heavy usage of fct_sales_pipeline from the Finance side. We need to coordinate any upcoming changes."
   - Another thread in `#sales-data` about lead_score accuracy
4. Verify all messages searchable via RTS

---

## Stream 6 – Integration & Demo Script

**Goal:** Validate the full pipeline and prepare the demo.

**Steps:**
1. `make setup && make seed-data && make dbt-run`
2. Start the app (`make run-app`)
3. Test trigger: "We're deprecating the lead_score column in fct_sales_pipeline next week"
4. Verify Block Kit card with accurate column-level lineage and stale thread detection
5. Test all buttons (channel creation, migration plan, thread updates)
6. Test Slackbot MCP Client: connect app, ask "What's the impact of dropping lead_score from fct_sales_pipeline?" *(MCP endpoint ready — Stream 3 ✅)*
7. Record 3-minute demo video
