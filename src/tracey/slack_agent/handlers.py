import asyncio
import json
import logging
import os
import re
from collections import Counter
from datetime import UTC, datetime

from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError

from tracey.agent.deps import TraceyDeps
from tracey.agent.loop import run_tracey_agent
from tracey.services.changelog_service import get_last_change
from tracey.services.lineage_service import (
    get_column_lineage,
    get_lineage,
    get_migration_order,
)
from tracey.services.test_service import get_tests
from tracey.services.usage_service import get_usage
from tracey.slack_agent.cards import (
    _actions_block,
    build_checklist_blocks,
    build_cross_team_summary_blocks,
    build_impact_card,
    build_markdown_summary,
    build_marked_outdated_confirmation,
    build_pr_confirmation_blocks,
    build_pr_modal,
    build_stale_thread_block,
)
from tracey.slack_agent.prefilter import has_model_mention as _prefilter_check
from tracey.slack_agent.session_store import SessionStore

logger = logging.getLogger(__name__)

session_store = SessionStore()

_MANIFEST_PATH = os.environ.get("MANIFEST_PATH", "dbt_project/target/manifest.json")
_DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "data/demo.duckdb")
_DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "dbt_project")
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
_SLACK_USER_TOKEN = os.environ.get("SLACK_USER_TOKEN", "")

_TARGET_CHANNEL_IDS: frozenset[str] = frozenset(
    cid.strip() for cid in os.environ.get("SLACK_TARGET_CHANNEL_IDS", "").split(",") if cid.strip()
)

_MAX_CACHE_SIZE = 100
_MAX_PROCESSED_SIZE = 1000

PROCESSED_MESSAGES: set[tuple[str, str]] = set()
_ANALYSIS_CACHE: dict[tuple[str, str], dict] = {}


def register_handlers(bolt_app: AsyncApp) -> None:
    """Register all message and action handlers on the Bolt app instance."""
    bolt_app.message(re.compile(r".*"))(handle_message)
    bolt_app.action("start_cross_team_review")(handle_start_cross_team_review)
    bolt_app.action("generate_migration_plan")(handle_generate_migration_plan)
    bolt_app.action("mark_as_outdated")(handle_mark_as_outdated)
    bolt_app.action("annotate_pr")(handle_annotate_pr)
    bolt_app.view("annotate_pr_modal")(handle_annotate_pr_submission)


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
    Claude-powered agent for intelligent intent detection. The agent owns
    the response — we stream its output and append action button blocks.
    """
    try:
        if event.get("subtype") is not None:
            return
        if event.get("bot_id") is not None:
            return

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
                "Tracing model dependencies...",
                "Checking downstream impacts...",
                "Gathering usage statistics...",
            ],
        )
        response_text, new_session_id = await run_tracey_agent(
            text,
            session_id=existing_session_id,
            deps=deps,
        )

        if new_session_id:
            session_store.set_session(channel_id, thread_ts, new_session_id)

        if response_text:
            streamer = await say_stream()
            await streamer.append(markdown_text=response_text)
            action_block = _actions_block(model_name, channel_id, message_ts)
            await streamer.stop(blocks=[action_block])

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
        "lineage": asyncio.to_thread(get_lineage, model, _MANIFEST_PATH),
        "migration_order": asyncio.to_thread(
            get_migration_order,
            model,
            _MANIFEST_PATH,
        ),
        "usage": asyncio.to_thread(get_usage, model, _DUCKDB_PATH),
        "last_change": asyncio.to_thread(get_last_change, model, _DUCKDB_PATH),
        "tests": asyncio.to_thread(get_tests, model, _MANIFEST_PATH),
    }

    if column:
        futures["column_lineage"] = asyncio.to_thread(
            get_column_lineage,
            model,
            column,
            _MANIFEST_PATH,
            _DBT_PROJECT_DIR,
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
    """Rank users by reply count in RTS search results."""
    user_counts: Counter[str] = Counter()
    for match in rts_results:
        user = match.get("author_user_id", "")
        if user:
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
    _ANALYSIS_CACHE[key] = analysis
    _trim_cache()
    return analysis


# ---- Action handlers ----


async def handle_start_cross_team_review(ack, body, client):
    """Handle the 'Start Cross-Team Review' button click."""
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

        result = await client.conversations_create(
            name=f"review-{model}",
            is_private=False,
        )
        new_channel_id = result["channel"]["id"]
        new_channel_name = result["channel"]["name"]

        triggering_user = body.get("user", {}).get("id", "")
        invite_users = list(set(experts + [triggering_user])) if triggering_user else experts
        if invite_users:
            try:
                await client.conversations_invite(
                    channel=new_channel_id,
                    users=invite_users,
                )
            except SlackApiError as exc:
                logger.warning("Failed to invite users to channel: %s", exc)

        summary_blocks = build_cross_team_summary_blocks(
            model,
            new_channel_name,
            experts,
            new_channel_id,
        )
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=summary_blocks,
            text=f"Cross-team review started for {model}",
        )

        try:
            pin_msg = await client.chat_postMessage(
                channel=new_channel_id,
                text=f"Cross-team review for {model} impact analysis",
                blocks=build_impact_card(analysis) if analysis else [],
            )
            await client.pins_add(
                channel=new_channel_id,
                timestamp=pin_msg["ts"],
            )
        except SlackApiError as exc:
            logger.warning("Failed to pin summary in new channel: %s", exc)

    except Exception:
        logger.exception("Error handling start_cross_team_review")
        await _send_error(client, body)


async def handle_generate_migration_plan(ack, body, client):
    """Handle the 'Generate Migration Plan' button click."""
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
        tests_result = analysis.get("tests", {})
        owned_tests = tests_result.get("tests", [])
        referential_tests = tests_result.get("referential_tests", [])

        blocks = build_checklist_blocks(
            migration_order,
            owned_tests,
            referential_tests,
            model,
        )

        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=blocks,
            text=f"Migration plan for {model}",
        )

    except Exception:
        logger.exception("Error handling generate_migration_plan")
        await _send_error(client, body)


async def handle_mark_as_outdated(ack, body, client):
    """Handle the 'Mark as Outdated' button click."""
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

        current_permalink = await _get_message_permalink(client, channel_id, message_ts)

        count = 0
        for thread in stale_threads:
            try:
                blocks = build_stale_thread_block(
                    thread["ts"],
                    thread["channel"],
                    thread.get("permalink", ""),
                    last_change_date,
                    current_permalink or "",
                )
                await client.chat_postMessage(
                    channel=thread["channel"],
                    thread_ts=thread["ts"],
                    blocks=blocks,
                    text="This discussion may be outdated.",
                )
                count += 1
            except SlackApiError as exc:
                logger.warning(
                    "Failed to mark stale thread %s as outdated: %s",
                    thread.get("ts"),
                    exc,
                )

        confirm_blocks = build_marked_outdated_confirmation(count)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=confirm_blocks,
            text=f"Marked {count} stale thread(s) as outdated.",
        )

    except Exception:
        logger.exception("Error handling mark_as_outdated")
        await _send_error(client, body)


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

        view = build_pr_modal(model)
        view["private_metadata"] = json.dumps(
            {
                "model_name": model,
                "impact_summary": impact_summary,
                "repo": _GITHUB_REPO,
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
    """Handle the modal submission for Annotate PR."""
    metadata_str = view.get("private_metadata", "{}")
    try:
        metadata = json.loads(metadata_str)
    except json.JSONDecodeError:
        logger.error("Invalid private_metadata in annotate_pr modal")
        await ack()
        return

    model_name = metadata.get("model_name", "unknown")
    impact_summary = metadata.get("impact_summary", "")
    repo = metadata.get("repo", _GITHUB_REPO)
    channel_id = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")

    state = view.get("state", {}).get("values", {})

    pr_id = state.get("pr_number_block", {}).get("pr_number_input", {}).get("value", "").strip()

    if not pr_id:
        await ack(
            {
                "response_action": "errors",
                "errors": {
                    "pr_number_block": "PR number is required.",
                },
            }
        )
        return

    custom_notes = state.get("custom_summary_block", {}).get("custom_summary_input", {}).get("value", "").strip()

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

        result = annotate_pr(pr_id, summary, repo, _GITHUB_TOKEN)

        if "error" in result:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f":warning: Failed to annotate PR: {result['error']}",
            )
            return

        pr_url = result.get("pr_url")
        confirm_blocks = build_pr_confirmation_blocks(
            pr_id,
            pr_url,
            model_name,
        )
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
