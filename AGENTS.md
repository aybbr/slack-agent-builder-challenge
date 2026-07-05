# Project Rules for AI Coding Agents

## Naming

- Never use "bot" to refer to the Slack agent. Always call it **slack agent**.
  - Script name: `slack-agent` (not `slack-bot`)
  - Make target: `run-slack-agent` (not `run-bot`)
  - Service name: `slack-agent` (not `bot`)

## Commands

- Run: `source .venv/bin/activate && uv sync --extra dev` to sync dependencies
- Test: `uv run python -m pytest`
- Lint: not configured yet
- Typecheck: not configured yet

## References

- Project roadmap: see ROADMAP.md

---

## Design Decisions

These are anchored architectural choices. All AI coding agents must respect them.

### MCP Framework
- Use **`fastmcp`** (community package `fastmcp`) for all MCP tool definitions.
  Import: `from fastmcp import FastMCP`
- `fastmcp` was chosen over the official `mcp` SDK because:
  - Protocol-compatible (JSON-RPC 2.0 over Streamable HTTP) — works with Slackbot MCP Client
  - Cleaner composability with Bolt via `http_app()` → `StarletteWithLifespan` (no manual lifespan wiring)
  - Popular community standard with richer feature set
- For MCP type annotations use `from mcp.types import ToolAnnotations` (from the official `mcp` SDK, which is a transitive dependency of `fastmcp`).

### MCP Authentication
- We use **`slack_identity_auth`** for the Slackbot MCP Client.
- Every request to `/mcp` is verified via `SlackSignatureMiddleware` (HMAC-SHA256 using the app signing secret).
- Slack injects `_meta.slack` with `user_id`, `team_id`, `enterprise_id` — no user OAuth needed.
- Required bot scopes: `mcp:connect`, `users:read`, `users:read.email`.
- For local development, set `TRACEY_SKIP_SIGNATURE_CHECK=1` to bypass verification.

### Deployment Architecture
- **Two Railway services** from the same repo, sharing one codebase.
  - **MCP service** (`tracey.app:main`): `GET /health`, `POST /mcp` — Streamable HTTP, Slack signature verified.
  - **Slack agent service** (`slack_agent/app.py:main`): `GET /health`, `POST /slack/events`, `POST /slack/interactivity` — Bolt HTTP.
- Both services import `services/` directly — no network hop between them, but they run in separate processes.
- Per-service start commands set via Railway dashboard UI. Shared `railway.json` provides base config (builder, health check pattern, restart policy).
- MCP entrypoint: `src/tracey/app.py` → `main()` → uvicorn on `0.0.0.0:$PORT`.
- Slack agent entrypoint: `src/tracey/slack_agent/app.py` → `main()` → uvicorn on `0.0.0.0:$PORT`.

### Interface Consistency
- **MCP tools** are thin wrappers: validate input → call service → return dict. One-line delegation to `services/`.
- Every tool must have: type-hinted signature, `ToolAnnotations(readOnlyHint=True)`, LLM-facing docstring, and input validation.
- **Services** remain pure: no Slack, no FastMCP, no I/O framework imports. Unit-testable without mocks.
- New agent capabilities always follow this layering:
  1. Add pure logic to `services/` (tested in isolation)
  2. Wrap in an MCP tool with `@mcp.tool` (thin adapter in `mcp_server/`)
  3. Optionally add a Slack handler in `slack_agent/` (UI layer)

---

## Architecture

Single Python package (`src/tracey/`) deployed as one Railway service:

| Directory | Purpose |
|-----------|---------|
| `src/tracey/services/` | Pure domain logic — no Slack, FastMCP, or I/O deps. All functions take explicit paths/tokens as args. |
| `src/tracey/mcp_server/` | MCP tools + Slack signature middleware — thin wrappers that read env vars and delegate to `services/` |
| `src/tracey/slack_agent/` | Slack Bolt agent — message listeners, Block Kit, interactivity (Stream 4) |
| `src/tracey/app.py` | Starlette entrypoint composing `/health`, `/mcp`, and (future) `/slack/events` routes |
| `src/tracey/utils/` | Shared helpers |
| `scripts/` | Standalone setup/seed scripts |
| `tests/` | Top-level pytest suite (mirrors `src/tracey/` structure) |
| `dbt_project/` | dbt models, profiles, manifest |

**Key rule:** `services/` modules must never import `fastmcp`, `mcp`, `slack_bolt`, or any I/O-heavy library. They are pure logic, unit-testable without mocks. Filesystem/DuckDB/network access happens only at the edges (MCP tools, Slack handlers, scripts).

## Python & Typing

- Target **Python 3.12**. Use modern syntax available in 3.12:
  - `X | None` instead of `Optional[X]`
  - Built-in generics: `list[int]`, `dict[str, int]`
  - `match`/`case` where it improves clarity
- No deprecated typing imports (`typing.List`, `typing.Dict`, `typing.Optional`)
- **All public functions must be fully type-hinted** including return types
- Use `dataclasses.dataclass(frozen=True, slots=True)` for DTOs/value objects
- Avoid `Any`; if unavoidable, isolate and comment why

---

## Code Style & Formatting

### Naming
- `snake_case` for functions, variables, modules, methods
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for module-level constants
- Leading underscore (`_`) for internal/private functions and attributes
- No cryptic abbreviations — names should describe intent, not implementation

### Formatting (Ruff)
- Target: **Ruff** for both formatting and linting (planned, not configured yet)
- 88 character line length (Ruff/Black default) unless overridden in `pyproject.toml`
- Use `uv run ruff format` and `uv run ruff check` when configured
- Agents must not reformat code by hand against Ruff's output — let the tool do it

### Imports
- Order: standard library → third-party → local (`tracey.*`)
- One import per line; no wildcard imports (`from module import *`)
- Sorted alphabetically within each group (Ruff/`isort` handles this)

### Whitespace
- No trailing whitespace; files end with a single newline
- One blank line between top-level definitions; two blank lines between classes and standalone functions
- Spaces around operators (`x = 1`, not `x=1`), after commas, but not inside brackets

---

## Pythonic & Idiomatic Code

Write code that is recognizably Pythonic — favor clarity over cleverness:

- **Comprehensions** over manual loops for building lists, dicts, sets:
  ```python
  # Prefer this
  scores = {name: compute_score(name) for name in names}
  # Over this
  scores = {}
  for name in names:
      scores[name] = compute_score(name)
  ```
  But fall back to a loop if the comprehension becomes unreadable (nested ternaries, multi-step logic).

- **Context managers** for resource lifecycle:
  ```python
  with duckdb.connect(db_path) as con:
      result = con.execute(query).fetchall()
  ```
  Always use `with` for files, connections, locks — anything with setup/teardown.

- **`enumerate` and `zip`** over index-based loops:
  ```python
  for i, item in enumerate(items): ...    # not range(len(items))
  for a, b in zip(list_a, list_b): ...    # not indexing into both
  ```

- **Unpacking** for cleaner assignments:
  ```python
  first, *middle, last = sequence
  key, value = pair
  ```

- **Generator expressions** for large or streaming data instead of materializing:
  ```python
  total = sum(row["amount"] for row in results)  # generator, not list comprehension
  ```

- **`collections` module** when the right data structure matters:
  - `defaultdict` for grouping/counting patterns
  - `Counter` for frequency counts
  - `deque` for efficient queue/stack operations

- Follow PEP 20: "Explicit is better than implicit," "Flat is better than nested," "Readability counts."

---

## Design

### Pure Functions First
- Prefer functions with no side effects: same input always produces same output, no mutation of arguments, no hidden I/O.
- Push I/O (filesystem, DuckDB, network, env vars) to the edges: MCP tools, Slack handlers, and scripts.
- `services/` is the pure core — functions there should be trivially testable with plain arguments.

### Composition Over Inheritance
- Use `Protocol` for dependency boundaries (not abstract base classes with deep hierarchies)
- Compose small, focused functions rather than building monolithic classes
- Apply SOLID pragmatically where classes are used (adapters, repositories):
  - **S**ingle Responsibility: one module, one reason to change
  - **O**pen/Closed: extend via new implementations of a `Protocol`, not by editing existing branches
  - **L**iskov Substitution: subtypes must be substitutable for their base
  - **I**nterface Segregation: small, focused `Protocol`s over large multi-purpose interfaces
  - **D**ependency Inversion: depend on abstractions, not concrete implementations; inject via constructor/function parameters, not global state

### Immutability
- Prefer `frozen=True` dataclasses, tuples, and `frozenset` for value objects
- Avoid mutable default arguments (`def func(items=None)` not `def func(items=[])`)
- Avoid shared mutable state; pass data explicitly

### DRY
- Extract shared logic into `services/` or `utils/` — never duplicate across MCP and Slack modules
- If you find yourself writing the same logic in `mcp_server/` and `slack_agent/`, it belongs in `services/`

### Defensive Copying
- When returning mutable data from a function that should not be mutated by the caller, copy it
- When accepting mutable data that the function may modify, copy it first if the caller may still need the original

---

## Docstrings & Comments

- Every public module, class, and function must have a docstring.
- Docstring format: purpose, parameters, return value, side effects (if any), exceptions raised.
- FastMCP tool docstrings double as the LLM-facing tool description — write them for that audience: clear, precise, describe what the tool does and what it returns.
- Comments explain *why*, not *what* (the code already says *what*).
- Keep comments current — stale comments are worse than none.

---

## Error Handling

- Catch specific exceptions only (`ValueError`, `KeyError`, `FileNotFoundError`) — never bare `except:`.
- Raise domain-specific exceptions where appropriate rather than letting raw library exceptions propagate across module boundaries.
- Use the `logging` module for diagnostics — never `print()` in library or server code.
  ```python
  import logging
  logger = logging.getLogger(__name__)
  logger.info("Processing asset %s", asset_id)
  ```
- In MCP tools and Slack handlers, translate internal exceptions into clear, safe user-facing responses. Never leak stack traces or internal details to the client.
- Fail fast: validate input early, don't continue processing with invalid data.

---

## Testing

- Use `pytest`. Tests in `tests/` mirror the `src/tracey/` structure.
- Test methods use `itShould_*` / `itShouldnt_*` naming convention (pytest configured via `python_functions` in `pyproject.toml`). Legacy `test_*` methods are also supported.
- Pure functions in `services/` should require minimal mocking — this is the payoff for the design above.
- For I/O code (DuckDB queries, HTTP calls, Slack API), isolate side effects behind a `Protocol` so tests can use fakes.
- Every new feature and bug fix requires tests.
- A bug fix must include a regression test that fails before the fix.
- Run tests with `uv run python -m pytest` or `make test`.

---

## Dependencies

- Minimize dependencies; prefer the standard library.
- Manage exclusively with `uv`:
  - Add deps: `uv add <package>`
  - Add dev deps: `uv add --dev <package>`
  - Never hand-edit `uv.lock` or `pyproject.toml` dependency lines.
- Never use `pip install`, `poetry`, or `requirements.txt`.
- Pin via `uv.lock` — let `uv` manage exact versions.

---

## Performance & Memory

- **Prefer generators over lists** for large or streaming data:
  ```python
  # Generator — memory-efficient for large result sets
  def iter_models(manifest): ...
  
  # Avoid materializing everything at once unless needed
  all_models = list(iter_models(manifest))  # only if you need random access
  ```
- Use generator expressions inside aggregators (`sum(row["amount"] for row in results)`) instead of building intermediate lists.
- **Lazy loading**: don't load an entire file or dataset if you only need a small slice. Use `LIMIT` in SQL, read JSON incrementally, parse only what you need.
- **Avoid O(n²)** patterns on collections that can grow large — prefer dict lookups (O(1)) over list scans (O(n)).
- **Optimize only with evidence**: don't sacrifice readability for speculative performance gains. Profile first (`cProfile`, `timeit`) then fix the bottleneck.
- Be mindful of memory in DuckDB queries — use `LIMIT` and `OFFSET` for pagination, don't `SELECT *` from large tables unnecessarily.

---

## Security

- Never use `eval`/`exec` on external or user-controlled input.
- Validate and sanitize all input at MCP tool boundaries (paths, table names, SQL fragments).
- Never log secrets, tokens, API keys, or credentials.
- Load secrets from environment variables, never hardcode them in source.
- Fail explicitly on invalid state — don't silently continue with partial or corrupt data.

---

## Agent Behavior

- Never fabricate API behavior — verify against actual docs or existing source code before using unfamiliar APIs.
- Make minimal, targeted diffs; don't reformat unrelated code in the same change.
- Respect package boundaries: logic used by both MCP and Slack modules belongs in `services/`.
- When adding a FastMCP tool, always include: type-hinted signature, docstring (tool description for LLMs), input validation, and a test.
- When unsure about module placement, interface design, or whether a change breaks public APIs, ask before proceeding.
- Commit and push only when explicitly asked.

---

## Slack Agent (Bolt for Python)

Use these rules when implementing or extending the Slack agent in `src/tracey/slack_agent/`. The Slack agent is a **trigger-detection + Block Kit workflow** — not a conversational AI assistant. See `ROADMAP.md` Stream 4 for the full spec.

### Architecture & Layering

- The Slack agent runs as its own standalone Starlette app (`src/tracey/slack_agent/app.py`) with `POST /slack/events` and `POST /slack/interactivity` routes. It does not share a process with the MCP service.
- **No Socket Mode** — use HTTP event delivery only.
- The Slack agent calls `services/` functions directly — no network hop, no MCP tool indirection. The MCP tools in `mcp_server/` are for external clients (Slackbot MCP Client); the Slack agent uses the same `services/` functions in-process.
- Keep Bolt handlers thin: parse Slack payload → call `services/` → build response. All business logic stays in `services/`.

### Trigger Detection

- Listen to channel messages (not app_mentions or DMs). Target channels: `#sales-data`, `#finance-data`, `#data-ops`.
- Detect change-intent by scanning message text for:
  - **Model names**: any mention of known dbt model names (e.g. `fct_sales_pipeline`, `fct_revenue_recognition`, `rpt_commissions`, `dim_customer`).
  - **Intent keywords**: `drop`, `remove`, `deprecate`, `rename`, `change`, `refactor`, `delete`, `modify`.
- Both conditions must be met to trigger. A mention of a model name alone is not a trigger; a keyword alone is not a trigger.
- Ignore non-relevant events: message edits (`subtype`), deletes, and messages from other bots (`bot_id` check).
- On trigger: add an `:eyes:` reaction to the triggering message. Track per-message so it's added only once.

### Analysis (Parallel Calls)

- After trigger detection, fire all analysis calls in parallel (using `asyncio.gather` or equivalent):
  1. `lineage_service.get_lineage(asset_id, manifest_path)` — upstream/downstream + cross-domain detection.
  2. `lineage_service.get_migration_order(asset_id, manifest_path)` — topologically sorted descendants.
  3. `lineage_service.get_column_lineage(asset_id, column_name, manifest_path, compiled_dir)` — if a specific column is mentioned.
  4. `usage_service.get_usage(asset_id, db_path)` — usage stats by domain.
  5. `changelog_service.get_last_change(asset_id, db_path)` — last schema change timestamp.
  6. `test_service.get_tests(asset_id, manifest_path)` — owned and referential tests.
  7. Slack RTS search for past threads mentioning the model (for stale thread detection).
- Pass `MANIFEST_PATH`, `DUCKDB_PATH`, `DBT_PROJECT_DIR` from environment variables.

### Stale Thread Detection & Expert Ranking

- Use Slack RTS (Real-Time Search) to find past threads mentioning the model name in relevant channels.
- Compare thread timestamps against `last_change_ts` from `get_last_change`: if a thread predates the last schema change, it's **stale**.
- Rank experts by counting replies per user in those threads. Top 3 become the suggested experts for cross-team review.

### Block Kit Cards

- Present results as a **single Block Kit message** (not a streaming response). Structure:
  1. **Header**: warning emoji + alert-style message (e.g. `:warning: Proposed change to fct_sales_pipeline`).
  2. **Structural Impact**: cross-domain downstream models, column-level lineage summary.
  3. **Usage Statistics**: per-domain usage counts from `get_usage`.
  4. **Migration Order**: preview of topologically sorted descendants from `get_migration_order`.
  5. **Social Impact**: @mentions for top experts, links to stale threads.
  6. **Action Buttons**: `Start Cross-Team Review`, `Generate Migration Plan`, `Mark as Outdated`, `Annotate PR`.
- Use `blocks` (Block Kit JSON), not `text` or `blocks` as text fallback. All buttons must have unique `action_id` values.
- Keep blocks under Slack's 50-block limit. Use `mrkdwn` formatting for readability.

### Interactive Button Handlers

- Every button handler follows this pattern:
  1. `ack()` — acknowledge the interaction immediately to prevent timeout.
  2. Perform action (create channel, post message, open modal, etc.).
  3. Update or reply with the result. Always surface errors as user-facing Slack messages with `:warning:`.

- **All action replies use Block Kit blocks** (sections, context, actions) — never plain text. This ensures a consistent, rich UX across the demo.

- **Start Cross-Team Review**:
  - Create a new Slack channel (or Thread if more appropriate) named `review-{model_name}`.
  - Invite top 3 experts and the triggering user.
  - Post a Block Kit summary into the original thread: header block, context block with the new channel link, and a section listing invited experts.
  - Pin a summary message in the new channel.

- **Generate Migration Plan**:
  - Post a structured checklist as a threaded Block Kit reply, built from `get_migration_order` and `get_tests` output.
  - Each step is a section block with emoji status (`:white_check_mark:` for passing tests, `:warning:` for warnings).
  - Include test status, downstream model list, and suggested order.

- **Mark as Outdated**:
  - For each stale thread, post a Block Kit outdated notice as a **threaded reply** within that thread. The notice includes a section block with the last change date and a context block linking to the current discussion.
  - Post a small Block Kit confirmation in the original thread (`"Marked N stale threads as outdated."`).

- **Annotate PR** — uses modal + thread confirmation:
  - On button click: `ack()` immediately, then `client.views_open(trigger_id=..., view=...)` to open a modal collecting:
    - PR number (plain text input).
    - Optional custom summary text (appended to the impact summary, never replaces it).
    - Checkbox: "Include full impact summary" (default checked).
  - Store context (`model_name`, `impact_summary`, `repo`, `token`) in `private_metadata` as JSON.
  - `@bolt_app.view("annotate_pr_modal")` handler:
    - `ack()` the submission.
    - Extract `pr_id` and `custom_notes` from `view["state"]["values"]`.
    - Call `github_service.annotate_pr(pr_id, summary, repo, token)` directly (not via MCP tool).
    - Post a Block Kit confirmation in the original thread: section block summarizing the annotated PR + context block with the PR link (from `annotate_pr` returned `pr_url`).

### Error Handling

- Wrap all handler logic in `try/except`; on failure log with `logger.exception(...)` and send a friendly error message to the user (with `:warning:` emoji).
- If the triggering message can't be parsed (no model detected, no intent keyword found), do not respond — the trigger detection should prevent this.
- Translate internal exceptions into clear, safe user-facing responses. Never leak stack traces, file paths, or internal details to Slack.
- Use the `logging` module for diagnostics — never `print()`.

### Environment & Secrets

- Load Slack tokens from environment variables: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`. Never hardcode.
- Additional env vars used by the Slack agent: `MANIFEST_PATH`, `DUCKDB_PATH`, `DBT_PROJECT_DIR`, `GITHUB_TOKEN`, `GITHUB_REPO`.
- For local development with Bolt HTTP, use a tunnel (ngrok or similar) to expose the `/slack/events` endpoint. The Slack App manifest must have the correct Request URL.

### Structure & Quality

- Organize code within `src/tracey/slack_agent/`:
  - `app.py` — Bolt app initialization and route mount.
  - `handlers.py` — message and action event handlers.
  - `triggers.py` — trigger detection logic (model name + intent keyword matching).
  - `cards.py` — Block Kit card builders (functions that return blocks dicts).
- Use type hints and docstrings for all public handler and builder functions.
- Target Ruff for formatting (not configured yet — see AGENTS.md §Formatting).

### Reference Docs

- Bolt for Python main docs: https://docs.slack.dev/tools/bolt-python/
- Bolt HTTP setup (no Socket Mode): https://docs.slack.dev/tools/bolt-python/getting-started-http/
- Block Kit builder & reference: https://docs.slack.dev/reference/block-kit/
- Interactive components (buttons, actions): https://docs.slack.dev/tools/bolt-python/concepts/interactivity/
- Slack RTS search: https://docs.slack.dev/reference/methods/search.messages
