import asyncio
import json
import logging
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError

from tracey.agent.deps import TraceyDeps
from tracey.agent.loop import run_tracey_agent
from tracey.services.changelog_service import get_last_change
from tracey.services.env_config import EnvConfig
from tracey.services.lineage_service import (
    get_column_lineage,
    get_lineage,
    get_migration_order,
)
from tracey.services.test_service import get_tests
from tracey.services.usage_service import get_usage
from tracey.slack_agent.cards import (
    _actions_block,
    _render_mermaid_to_slack,
    build_checklist_blocks,
    build_close_pr_modal,
    build_cross_team_section,
    build_cross_team_summary_blocks,
    build_downstream_section,
    build_feedback_blocks,
    build_impact_header,
    build_markdown_summary,
    build_marked_outdated_confirmation,
    build_migration_diagram_syntax,
    build_migration_modal,
    build_migration_preview_section,
    build_outdated_modal,
    build_plan_block,
    build_pr_closed_confirmation_blocks,
    build_pr_confirmation_blocks,
    build_pr_modal,
    build_review_modal,
    build_stale_thread_block,
    build_usage_section,
)
from tracey.slack_agent.prefilter import has_model_mention as _prefilter_check
from tracey.slack_agent.session_store import SessionStore

logger = logging.getLogger(__name__)

session_store = SessionStore()

_ENV = EnvConfig.from_env()

_SLACK_USER_TOKEN = os.environ.get("SLACK_USER_TOKEN", "")

_TARGET_CHANNEL_IDS: frozenset[str] = frozenset(
    cid.strip() for cid in os.environ.get("SLACK_TARGET_CHANNEL_IDS", "").split(",") if cid.strip()
)

_BOT_USER_ID: str = "A0BF7MKNEN5"

_MAX_CACHE_SIZE = 100
_MAX_PROCESSED_SIZE = 1000

PROCESSED_MESSAGES: set[tuple[str, str]] = set()
_ANALYSIS_CACHE: dict[tuple[str, str], dict] = {}

_SEEDED_ANALYSIS_PATH = Path("data/seeded_analysis.json")


def _load_seeded_analysis() -> dict:
    """Load pre-computed seeded analysis data from the seeding script."""
    if not _SEEDED_ANALYSIS_PATH.exists():
        return {}
    try:
        return json.loads(_SEEDED_ANALYSIS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def register_handlers(bolt_app: AsyncApp) -> None:
    """Register all message and action handlers on the Bolt app instance."""
    bolt_app.message(re.compile(r".*"))(handle_message)
    bolt_app.action("start_cross_team_review")(handle_start_cross_team_review)
    bolt_app.action("generate_migration_plan")(handle_generate_migration_plan)
    bolt_app.action("mark_as_outdated")(handle_mark_as_outdated)
    bolt_app.action("annotate_pr")(handle_annotate_pr)
    bolt_app.action("close_pr")(handle_close_pr)
    bolt_app.view("annotate_pr_modal")(handle_annotate_pr_submission)
    bolt_app.view("close_pr_modal")(handle_close_pr_submission)
    bolt_app.view("review_modal")(handle_review_modal_submission)
    bolt_app.view("outdated_modal")(handle_outdated_modal_submission)
    bolt_app.view("migration_modal")(handle_migration_modal_submission)


_ACTIONS_MARKER_RE = re.compile(r"<!--actions\s*(.*?)\s*-->", re.DOTALL)


def _parse_actions_marker(text: str) -> tuple[str, dict]:
    """Extract and remove the actions marker from the agent's response.

    Returns ``(cleaned_text, marker_data)`` where ``marker_data`` is a dict
    with keys ``visible`` (``set[str]`` of action keys) and ``pr_number``
    (``str | None``, the extracted PR number from any GitHub URL in the
    message).  Returns ``{"visible": set()}`` on missing/unparseable marker.
    """
    empty: dict = {"visible": set(), "pr_number": None}
    match = _ACTIONS_MARKER_RE.search(text)
    if not match:
        return text, empty

    marker_text = match.group(1).strip()
    cleaned = text[: match.start()] + text[match.end() :]

    try:
        parsed = json.loads(marker_text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse actions marker: %s", marker_text[:80])
        return cleaned, empty

    visible: set[str] = set()
    for key in ("review", "migration", "outdated", "pr", "close_pr"):
        if parsed.get(key) is True:
            visible.add(key)

    pr_number = str(parsed["pr_number"]).strip() if parsed.get("pr_number") else None

    return cleaned.strip(), {"visible": visible, "pr_number": pr_number}


# ---- Message handler ----


async def handle_message(
    event: dict,
    client,
    say_stream,
    set_status,
    context,
) -> None:
    """Handle incoming channel messages with prefilter gate and LLM agent.

    The prefilter cheaply detects model mentions; when found, invokes the
    Claude-powered agent for intelligent intent detection.  Real-time plan
    blocks are posted and updated as the agent calls tools.  After the
    agent finishes, context-aware action buttons are derived from the
    agent's response marker.
    """
    global _BOT_USER_ID
    if not _BOT_USER_ID:
        _BOT_USER_ID = context.get("bot_user_id", "")
    try:
        if event.get("subtype") is not None:
            return {"ok": True}
        if event.get("bot_id") is not None:
            return {"ok": True}

        channel_id = event.get("channel", "")
        message_ts = event.get("ts", "")
        text = event.get("text", "")

        if not _is_target_channel(channel_id):
            return

        cache_key = (channel_id, message_ts)
        if cache_key in PROCESSED_MESSAGES:
            return

        model_name = _prefilter_check(text)
        if model_name is None:
            return

        logger.info(
            "Model mention detected — model=%s channel=%s user=%s",
            model_name,
            channel_id,
            event.get("user", "?"),
        )

        PROCESSED_MESSAGES.add(cache_key)
        _trim_processed()

        _ANALYSIS_CACHE[cache_key] = {
            "model": model_name,
            "channel_id": channel_id,
            "message_ts": message_ts,
        }
        _trim_cache()

        thread_ts = event.get("thread_ts", message_ts)
        deps = TraceyDeps(
            client=client,
            user_id=event.get("user", ""),
            channel_id=channel_id,
            thread_ts=thread_ts,
            message_ts=message_ts,
            user_token=_SLACK_USER_TOKEN,
        )

        existing_session_id = session_store.get_session(channel_id, thread_ts)
        await set_status(
            status="Analysing impact...",
            loading_messages=[
                "Following the breadcrumbs...",
                "Drawing the lineage graph...",
                "Interrogating source tables (politely)...",
                "Checking if anyone still uses this...",
                "Making sure CFO's favorite chart won't break...",
            ],
        )

        # ---- Real-time plan blocks ----
        plan_tasks: list[dict] = []
        plan_message_ts: str | None = None

        async def _on_plan_update(task_id: str, tool_name: str, status: str) -> None:
            """Called by the agent loop each time a tool starts or finishes."""
            nonlocal plan_message_ts
            existing = next((t for t in plan_tasks if t["task_id"] == task_id), None)
            if existing:
                existing["status"] = status
            else:
                plan_tasks.append({"task_id": task_id, "name": tool_name, "status": status})

            try:
                blocks = [build_plan_block(plan_tasks)]
                if plan_message_ts:
                    await client.chat_update(channel=channel_id, ts=plan_message_ts, blocks=blocks, text="thinking..")
                else:
                    resp = await client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        blocks=blocks,
                        text="Agent thinking steps",
                    )
                    plan_message_ts = resp["ts"]
            except SlackApiError:
                logger.debug("Plan block update skipped (may not be supported yet)")

        response_text, new_session_id = await run_tracey_agent(
            text,
            session_id=existing_session_id,
            deps=deps,
            on_plan_update=_on_plan_update,
        )

        if new_session_id:
            session_store.set_session(channel_id, thread_ts, new_session_id)

        # Populate analysis cache before showing buttons so action
        # handlers have consistent data without re-running RTS searches.
        analysis = await _get_or_create_analysis(model_name, channel_id, message_ts, client)

        if response_text:
            cleaned_text, marker_data = _parse_actions_marker(response_text)
            if marker_data.get("pr_number"):
                _ANALYSIS_CACHE[cache_key]["pr_number"] = marker_data["pr_number"]
            visible = marker_data.get("visible", set()) or None
            blocks = _build_response_blocks(
                analysis or {},
                model_name,
                channel_id,
                message_ts,
                visible_actions=visible,
            )
            streamer = await say_stream()
            await streamer.append(markdown_text=cleaned_text or response_text)
            await streamer.stop(blocks=blocks)

    except Exception:
        logger.exception("Error handling message in channel %s", event.get("channel"))
        try:
            await client.chat_postMessage(
                channel=event.get("channel", ""),
                thread_ts=event.get("ts", ""),
                text=":warning: Something went wrong while analysing the impact. Please try again.",
            )
        except Exception:
            logger.exception("Failed to send error message")


# ---- Analysis orchestration (lazy: called on-demand by action handlers) ----


def _build_response_blocks(
    analysis: dict,
    model_name: str,
    channel_id: str,
    message_ts: str,
    visible_actions: set[str] | None = None,
) -> list[dict]:
    """Build the full Block Kit response from analysis data.

    Args:
        analysis: Dict with lineage, usage, migration, experts, stale_threads.
        model_name: The dbt model name.
        channel_id: Slack channel ID.
        message_ts: Message timestamp.
        visible_actions: Optional set of action IDs to show (e.g.
            ``{"review", "migration", "outdated", "pr"}``).  When ``None``,
            all four buttons are rendered (backward-compatible fallback).
    """
    lineage = analysis.get("lineage", {})
    downstream: list = lineage.get("downstream", [])
    cross_count = sum(1 for d in downstream if d.get("cross_domain"))
    domain = lineage.get("domain", "")

    blocks: list[dict] = []

    header = build_impact_header(model_name, len(downstream), cross_count, domain)
    blocks.extend(header)

    ds_section = build_downstream_section(downstream)
    if ds_section:
        blocks.extend(ds_section)

    usage = analysis.get("usage", {})
    usage_section = build_usage_section(usage)
    if usage_section:
        blocks.extend(usage_section)

    migration = analysis.get("migration_order", {})
    mig_section = build_migration_preview_section(migration)
    if mig_section:
        blocks.extend(mig_section)

    cross_team = build_cross_team_section(
        analysis.get("experts", []),
        analysis.get("stale_threads", []),
    )
    if cross_team:
        blocks.extend(cross_team)

    actions = _actions_block(model_name, channel_id, message_ts, visible=visible_actions)
    if actions:
        blocks.append(actions)
    blocks.extend(build_feedback_blocks())

    return blocks


async def _run_analysis(
    model: str,
    column: str | None,
    client,
) -> dict:
    """Run all analysis tasks in parallel via asyncio.gather.

    Uses ``asyncio.to_thread`` for synchronous service calls and
    named futures to avoid fragile index arithmetic.
    """
    futures: dict[str, asyncio.Future] = {
        "lineage": asyncio.to_thread(get_lineage, model, _ENV.manifest_path),
        "migration_order": asyncio.to_thread(
            get_migration_order,
            model,
            _ENV.manifest_path,
        ),
        "usage": asyncio.to_thread(get_usage, model, _ENV.duckdb_path),
        "last_change": asyncio.to_thread(get_last_change, model, _ENV.duckdb_path),
        "tests": asyncio.to_thread(get_tests, model, _ENV.manifest_path),
    }

    if column:
        futures["column_lineage"] = asyncio.to_thread(
            get_column_lineage,
            model,
            column,
            _ENV.manifest_path,
            _ENV.dbt_project_dir,
        )

    futures["slack"] = asyncio.ensure_future(
        _search_slack_threads(model),
    )

    results = await asyncio.gather(
        *futures.values(),
        return_exceptions=True,
    )
    analysis: dict = dict(zip(futures.keys(), results, strict=True))

    last_change = analysis.get("last_change", {})

    last_change_ts = None
    lc = last_change.get("last_change")
    if lc and isinstance(lc, dict):
        last_change_ts = lc.get("changed_at")

    rts_results = analysis.pop("slack", [])
    if isinstance(rts_results, BaseException):
        logger.warning("RTS search failed: %s", rts_results)
        rts_results = []
    analysis["stale_threads"] = _detect_stale_threads(rts_results, last_change_ts)
    analysis["experts"] = _rank_experts(rts_results)

    return analysis


async def _search_slack_threads(model: str) -> list[dict]:
    """Search Slack for past threads mentioning the model via RTS API."""
    if not _SLACK_USER_TOKEN:
        logger.warning("SLACK_USER_TOKEN not set, skipping RTS search")
        return []
    try:
        from slack_sdk.web.async_client import AsyncWebClient

        rts_client = AsyncWebClient(token=_SLACK_USER_TOKEN)
        response = await rts_client.api_call(
            api_method="assistant.search.context",
            http_verb="POST",
            json={
                "query": model,
                "content_types": ["messages"],
                "channel_types": ["public_channel"],
                "sort": "timestamp",
                "sort_dir": "desc",
                "limit": 20,
                "include_bots": True,
            },
        )
        return response.get("results", {}).get("messages", [])
    except SlackApiError as exc:
        logger.warning("Slack RTS search failed for %s: %s", model, exc)
        return []


def _detect_stale_threads(
    rts_results: list[dict],
    last_change_ts: str | None,
) -> list[dict]:
    """Identify threads that predate the last schema change."""
    if not last_change_ts:
        return []

    try:
        threshold = datetime.fromisoformat(last_change_ts).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        logger.warning("Invalid last_change_ts: %s", last_change_ts)
        return []

    stale: list[dict] = []
    seen_channels: set[str] = set()

    for match in rts_results:
        channel_id = match.get("channel_id", "")
        thread_ts = match.get("message_ts", "")

        if not thread_ts:
            continue

        try:
            thread_dt = _ts_to_datetime(thread_ts)
        except (ValueError, TypeError):
            continue

        if thread_dt < threshold and channel_id not in seen_channels:
            seen_channels.add(channel_id)
            stale.append(
                {
                    "ts": thread_ts,
                    "channel": channel_id,
                    "permalink": match.get("permalink", ""),
                }
            )

    return stale


def _rank_experts(rts_results: list[dict]) -> list[str]:
    """Rank users by reply count in RTS search results, excluding the bot."""
    user_counts: Counter[str] = Counter()
    for match in rts_results:
        user = match.get("author_user_id", "")
        if user and user != _BOT_USER_ID:
            user_counts[user] += 1

    top_users = [user for user, _ in user_counts.most_common(3)]
    return top_users


def _ts_to_datetime(ts: str) -> datetime:
    """Convert a Slack timestamp (e.g. '1687531200.123456') to datetime."""
    return datetime.fromtimestamp(float(ts), tz=UTC)


# ---- Lazy analysis helper for action handlers ----


async def _get_or_create_analysis(
    model: str,
    channel_id: str,
    message_ts: str,
    client,
) -> dict | None:
    """Return cached analysis or lazily build it on first request.

    Action handlers call this instead of looking up the cache directly,
    so that analysis runs only when a user actually clicks a button.
    Merges seeded analysis data when available for demo scenarios.
    """
    key = (channel_id, message_ts)
    cached = _ANALYSIS_CACHE.get(key) or {}

    if "lineage" in cached:
        return cached

    try:
        analysis = await _run_analysis(model, None, client)
    except Exception:
        logger.exception("Lazy analysis failed for model=%s", model)
        return None

    analysis["model"] = model
    analysis["channel_id"] = channel_id
    analysis["message_ts"] = message_ts

    seeded = _load_seeded_analysis().get(model)
    if seeded:
        if seeded.get("expert_names"):
            analysis["experts"] = seeded["expert_names"]
        if seeded.get("stale_threads"):
            analysis["stale_threads"] = seeded["stale_threads"]
        if seeded.get("last_change_date") and (
            "last_change" not in analysis or not analysis["last_change"].get("last_change")
        ):
            analysis["last_change"] = {"last_change": {"changed_at": seeded["last_change_date"]}}

    _ANALYSIS_CACHE[key] = analysis
    _trim_cache()
    return analysis


# ---- Action handlers ----


async def handle_start_cross_team_review(ack, body, client):
    """Open a modal for configuring the cross-team review."""
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = await _get_or_create_analysis(model, channel_id, message_ts, client)
        experts = analysis.get("experts", []) if analysis else []

        view = build_review_modal(model, experts, channel_id, message_ts)
        await client.views_open(trigger_id=body["trigger_id"], view=view)

    except Exception:
        logger.exception("Error opening review modal")
        await _send_error(client, body)


async def handle_review_modal_submission(ack, body, client, view):
    """Handle the review modal submission — create channel with verified experts."""
    metadata = json.loads(view.get("private_metadata", "{}"))
    model = metadata.get("model", "")
    original_channel = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")
    suggested_name = metadata.get("suggested_name", f"review-{model}")

    state = view.get("state", {}).get("values", {})
    selected_users = state.get("experts_block", {}).get("experts_select", {}).get("selected_users", [])
    selected_users = [u for u in selected_users if u != _BOT_USER_ID]
    notes = (state.get("notes_block", {}).get("notes_input", {}).get("value") or "").strip()

    await ack()

    try:
        result = await client.conversations_create(name=suggested_name, is_private=False)
    except SlackApiError as exc:
        if "name_taken" in str(exc):
            from datetime import datetime

            fallback = f"review-{model}-{datetime.now().strftime('%y%m%d%H%M%S')}"
            result = await client.conversations_create(name=fallback, is_private=False)
        else:
            logger.exception("Failed to create review channel")
            return

    new_channel_id = result["channel"]["id"]
    new_channel_name = result["channel"]["name"]

    triggering_user = body.get("user", {}).get("id", "")
    invite_users = list(set(selected_users + [triggering_user])) if triggering_user else selected_users
    if invite_users:
        try:
            await client.conversations_invite(channel=new_channel_id, users=",".join(invite_users))
        except SlackApiError as exc:
            logger.warning("Failed to invite users: %s", exc)

    analysis = await _get_or_create_analysis(model, original_channel, message_ts, client)
    summary_blocks = build_cross_team_summary_blocks(model, new_channel_name, selected_users, new_channel_id)
    await client.chat_postMessage(
        channel=original_channel,
        thread_ts=message_ts,
        blocks=summary_blocks,
        text=f"Cross-team review started for {model}",
    )

    if notes:
        await client.chat_postMessage(
            channel=new_channel_id,
            text=f"Review notes: {notes}",
        )

    try:
        pin_msg = await client.chat_postMessage(
            channel=new_channel_id,
            text=f"Cross-team review for {model} impact analysis",
            blocks=build_checklist_blocks(
                (analysis.get("migration_order", {}) if analysis else {}).get("migration_order", []),
                [],
                [],
                model,
            ),
        )
        await client.pins_add(channel=new_channel_id, timestamp=pin_msg["ts"])
    except SlackApiError as exc:
        logger.warning("Failed to pin summary: %s", exc)


async def handle_generate_migration_plan(ack, body, client):
    """Open a modal for confirming migration plan generation."""
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = await _get_or_create_analysis(model, channel_id, message_ts, client)

        if analysis is None:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=":warning: Analysis data is not available. Please try again.",
            )
            return

        migration_order = analysis.get("migration_order", {}).get("migration_order", [])
        view = build_migration_modal(model, migration_order, channel_id, message_ts)
        await client.views_open(trigger_id=body["trigger_id"], view=view)

    except Exception:
        logger.exception("Error opening migration modal")
        await _send_error(client, body)


async def handle_migration_modal_submission(ack, body, client, view):
    """Handle migration modal submission — post sorted diagram and checklist."""
    metadata = json.loads(view.get("private_metadata", "{}"))
    model = metadata.get("model", "")
    channel_id = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")

    state = view.get("state", {}).get("values", {})
    selected_opts = state.get("steps_block", {}).get("steps_checkbox", {}).get("selected_options", [])
    selected_ids = [opt.get("value", "") for opt in selected_opts]
    notes = (state.get("notes_block", {}).get("notes_input", {}).get("value") or "").strip()

    await ack()

    analysis = await _get_or_create_analysis(model, channel_id, message_ts, client)
    if analysis is None:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=":warning: Analysis data is not available.",
        )
        return

    full_order = analysis.get("migration_order", {}).get("migration_order", [])
    filtered = [s for s in full_order if s.get("id") in selected_ids] if selected_ids else full_order
    lineage = analysis.get("lineage", {})

    # Post the topological sort diagram first
    diagram_url = None
    if full_order:
        try:
            syntax = build_migration_diagram_syntax(model, full_order, lineage)
            diagram_url = await _render_mermaid_to_slack(
                syntax,
                f"Migration Order — {model}",
                channel_id,
                message_ts,
                client,
            )
        except Exception:
            logger.exception("Failed to render migration diagram for %s", model)

    tests_result = analysis.get("tests", {})
    blocks = build_checklist_blocks(
        filtered,
        tests_result.get("tests", []),
        tests_result.get("referential_tests", []),
        model,
    )

    if diagram_url:
        blocks.insert(
            0,
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f":mermaid: <{diagram_url}|View full-resolution diagram>",
                    }
                ],
            },
        )

    if notes:
        blocks.insert(
            1,
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Notes:* {notes}"},
            },
        )

    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        blocks=blocks,
        text=f"Migration plan for {model}",
    )


async def handle_mark_as_outdated(ack, body, client):
    """Open a modal for selecting stale threads to mark as outdated."""
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = await _get_or_create_analysis(model, channel_id, message_ts, client)

        if analysis is None:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=":warning: Analysis data is not available. Please try again.",
            )
            return

        stale_threads = analysis.get("stale_threads", [])
        last_change = analysis.get("last_change", {})
        last_change_data = last_change.get("last_change", {}) or {}
        last_change_date = last_change_data.get("changed_at", "unknown date")

        view = build_outdated_modal(model, stale_threads, last_change_date, channel_id, message_ts)
        await client.views_open(trigger_id=body["trigger_id"], view=view)

    except Exception:
        logger.exception("Error opening outdated modal")
        await _send_error(client, body)


async def handle_outdated_modal_submission(ack, body, client, view):
    """Handle outdated modal submission — mark selected threads."""
    metadata = json.loads(view.get("private_metadata", "{}"))
    _model = metadata.get("model", "")
    channel_id = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")
    last_change_date = metadata.get("last_change_date", "unknown date")

    state = view.get("state", {}).get("values", {})
    selected_opts = state.get("threads_block", {}).get("threads_checkbox", {}).get("selected_options", [])

    await ack()

    current_permalink = await _get_message_permalink(client, channel_id, message_ts)

    count = 0
    for opt in selected_opts:
        try:
            thread_data = json.loads(opt.get("value", "{}"))
            blocks = build_stale_thread_block(
                thread_data["ts"],
                thread_data["channel"],
                "",
                last_change_date,
                current_permalink or "",
            )
            await client.chat_postMessage(
                channel=thread_data["channel"],
                thread_ts=thread_data["ts"],
                blocks=blocks,
                text="This discussion may be outdated.",
            )
            count += 1
        except (json.JSONDecodeError, SlackApiError, KeyError) as exc:
            logger.warning("Failed to mark stale thread: %s", exc)

    confirm_blocks = build_marked_outdated_confirmation(count)
    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=message_ts,
        blocks=confirm_blocks,
        text=f"Marked {count} stale thread(s) as outdated.",
    )


async def handle_annotate_pr(ack, body, client):
    """Handle the 'Annotate PR' button click."""
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = await _get_or_create_analysis(model, channel_id, message_ts, client)

        impact_summary = ""
        if analysis:
            impact_summary = build_markdown_summary(analysis)

        pr_number = _ANALYSIS_CACHE.get((channel_id, message_ts), {}).get("pr_number")

        view = build_pr_modal(model, pr_number=pr_number)
        view["private_metadata"] = json.dumps(
            {
                "model_name": model,
                "impact_summary": impact_summary,
                "repo": _ENV.github_repo,
                "channel_id": channel_id,
                "message_ts": message_ts,
            }
        )

        await client.views_open(
            trigger_id=body["trigger_id"],
            view=view,
        )

    except Exception:
        logger.exception("Error opening annotate PR modal")
        await _send_error(client, body)


async def handle_annotate_pr_submission(ack, body, client, view):
    """Handle the modal submission for Annotate PR.

    Parses all inputs with null-safety, validates, acks early to close the
    modal, then performs the slow GitHub API call and posts confirmation.
    """
    metadata_str = view.get("private_metadata", "{}")
    try:
        metadata = json.loads(metadata_str)
    except json.JSONDecodeError:
        logger.error("Invalid private_metadata in annotate_pr modal")
        await ack()
        return

    model_name = metadata.get("model_name", "unknown")
    impact_summary = metadata.get("impact_summary", "")
    repo = metadata.get("repo", _ENV.github_repo)
    channel_id = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")

    state = view.get("state", {}).get("values", {})

    pr_id = (state.get("pr_number_block", {}).get("pr_number_input", {}).get("value") or "").strip()

    if not pr_id:
        await ack(
            {
                "response_action": "errors",
                "errors": {"pr_number_block": "PR number is required."},
            }
        )
        return

    custom_notes = (state.get("custom_summary_block", {}).get("custom_summary_input", {}).get("value") or "").strip()

    labels_raw = (state.get("labels_block", {}).get("labels_input", {}).get("value") or "do not merge").strip()

    labels = [lb.strip() for lb in labels_raw.split(",") if lb.strip()] if labels_raw else []

    include_full = False
    checkbox_block = state.get("include_summary_block", {})
    selected = checkbox_block.get("include_summary_checkbox", {}).get("selected_options", [])
    include_full = any(opt.get("value") == "include_full_summary" for opt in selected)

    await ack()

    try:
        from tracey.services.github_service import annotate_pr

        summary = ""
        if include_full and impact_summary:
            summary += impact_summary
        if custom_notes:
            if summary:
                summary += "\n\n---\n\n"
            summary += custom_notes
        if not summary:
            summary = f"Impact analysis for `{model_name}`."

        result = await asyncio.to_thread(annotate_pr, pr_id, summary, repo, _ENV.github_token, labels=labels)

        if "error" in result:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f":warning: Failed to annotate PR: {result['error']}",
            )
            return

        pr_url = result.get("pr_url")
        confirm_blocks = build_pr_confirmation_blocks(pr_id, pr_url, model_name)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=confirm_blocks,
            text=f"Annotated PR #{pr_id} for {model_name}",
        )

    except Exception:
        logger.exception("Error annotating PR %s", pr_id)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=":warning: An unexpected error occurred while annotating the PR.",
        )


async def handle_close_pr(ack, body, client):
    """Handle the 'Close PR' button click — open the close confirmation modal."""
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]

        pr_number = _ANALYSIS_CACHE.get((channel_id, message_ts), {}).get("pr_number")

        view = build_close_pr_modal(model, pr_number=pr_number)
        view["private_metadata"] = json.dumps(
            {
                "model_name": model,
                "repo": _ENV.github_repo,
                "channel_id": channel_id,
                "message_ts": message_ts,
            }
        )

        await client.views_open(
            trigger_id=body["trigger_id"],
            view=view,
        )

    except Exception:
        logger.exception("Error opening close PR modal")
        await _send_error(client, body)


async def handle_close_pr_submission(ack, body, client, view):
    """Handle the modal submission for Close PR.

    Parses inputs with null-safety, validates the PR number, acks early to
    close the modal, then performs the slow GitHub API call and posts
    confirmation.
    """
    metadata_str = view.get("private_metadata", "{}")
    try:
        metadata = json.loads(metadata_str)
    except json.JSONDecodeError:
        logger.error("Invalid private_metadata in close_pr modal")
        await ack()
        return

    model_name = metadata.get("model_name", "unknown")
    repo = metadata.get("repo", _ENV.github_repo)
    channel_id = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")

    state = view.get("state", {}).get("values", {})

    pr_id = (state.get("pr_number_block", {}).get("pr_number_input", {}).get("value") or "").strip()

    if not pr_id:
        await ack(
            {
                "response_action": "errors",
                "errors": {"pr_number_block": "PR number is required."},
            }
        )
        return

    comment = (state.get("close_comment_block", {}).get("close_comment_input", {}).get("value") or "").strip()

    await ack()

    try:
        from tracey.services.github_service import close_pr

        result = await asyncio.to_thread(close_pr, pr_id, repo, _ENV.github_token, comment=comment or None)

        if "error" in result:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f":warning: Failed to close PR: {result['error']}",
            )
            return

        pr_url = result.get("pr_url")
        confirm_blocks = build_pr_closed_confirmation_blocks(pr_id, pr_url, model_name)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=confirm_blocks,
            text=f"Closed PR #{pr_id} for {model_name}",
        )

    except Exception:
        logger.exception("Error closing PR %s", pr_id)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            text=":warning: An unexpected error occurred while closing the PR.",
        )


# ---- Helpers ----


def _is_target_channel(channel_id: str) -> bool:
    if not _TARGET_CHANNEL_IDS:
        return True
    return channel_id in _TARGET_CHANNEL_IDS


def _parse_action_value(body: dict) -> dict | None:
    """Extract context dict from a button action's ``value`` field."""
    try:
        actions = body.get("actions", [{}])
        value = actions[0].get("value", "{}")
        return json.loads(value)
    except (json.JSONDecodeError, IndexError, KeyError):
        logger.warning("Failed to parse action value from body")
        return None


async def _send_error(client, body: dict) -> None:
    """Send a generic error message to the user in the original thread."""
    try:
        channel = body.get("channel", {}).get("id", "")
        thread_ts = body.get("message", {}).get("thread_ts", "")
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=":warning: Something went wrong. Please try again.",
        )
    except Exception:
        logger.exception("Failed to send error message to user")


async def _get_message_permalink(client, channel_id: str, message_ts: str) -> str | None:
    """Resolve a message permalink via chat.getPermalink."""
    try:
        response = await client.chat_getPermalink(
            channel=channel_id,
            message_ts=message_ts,
        )
        return response.get("permalink")
    except SlackApiError:
        return None


def _trim_processed() -> None:
    """Evict oldest entries from PROCESSED_MESSAGES when over capacity."""
    while len(PROCESSED_MESSAGES) > _MAX_PROCESSED_SIZE:
        PROCESSED_MESSAGES.pop()


def _trim_cache() -> None:
    """Evict oldest entries from _ANALYSIS_CACHE when over capacity."""
    while len(_ANALYSIS_CACHE) > _MAX_CACHE_SIZE:
        _ANALYSIS_CACHE.pop(next(iter(_ANALYSIS_CACHE)))
