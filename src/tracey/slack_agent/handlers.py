import asyncio
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone

from slack_sdk.errors import SlackApiError

from tracey.services.changelog_service import get_last_change
from tracey.services.lineage_service import (
    get_column_lineage,
    get_lineage,
    get_migration_order,
)
from tracey.services.test_service import get_tests
from tracey.services.usage_service import get_usage
from tracey.slack_agent.cards import (
    build_checklist_blocks,
    build_cross_team_summary_blocks,
    build_impact_card,
    build_markdown_summary,
    build_marked_outdated_confirmation,
    build_pr_confirmation_blocks,
    build_pr_modal,
    build_stale_thread_block,
)
from tracey.slack_agent.triggers import detect_trigger

logger = logging.getLogger(__name__)

_MANIFEST_PATH = os.environ.get("MANIFEST_PATH", "dbt_project/target/manifest.json")
_DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "data/demo.duckdb")
_DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "dbt_project")
_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
_SLACK_USER_TOKEN = os.environ.get("SLACK_USER_TOKEN", "")

_TARGET_CHANNEL_IDS: frozenset[str] = frozenset(
    cid.strip()
    for cid in os.environ.get("SLACK_TARGET_CHANNEL_IDS", "").split(",")
    if cid.strip()
)

_MAX_CACHE_SIZE = 100
_MAX_PROCESSED_SIZE = 1000

PROCESSED_MESSAGES: set[tuple[str, str]] = set()
_ANALYSIS_CACHE: dict[tuple[str, str], dict] = {}


def register_handlers(bolt_app) -> None:
    """Register all message and action handlers on the Bolt app instance.

    Args:
        bolt_app: An ``AsyncApp`` instance from ``slack_bolt``.
    """
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
    say,
    context,
) -> None:
    """Handle incoming channel messages for trigger detection and analysis.

    Skips bot messages, edits, and messages outside target channels.
    On trigger, fires parallel analysis, builds a Block Kit impact card,
    and posts it to the channel.

    Args:
        event: Slack event payload.
        client: ``slack_sdk.web.async_client.AsyncWebClient``.
        say: Bolt ``say()`` utility for posting messages.
        context: Bolt context dict.
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

        trigger = detect_trigger(text)
        if trigger is None:
            return

        PROCESSED_MESSAGES.add(cache_key)
        _trim_processed()

        try:
            await client.reactions_add(
                channel=channel_id,
                timestamp=message_ts,
                name="eyes",
            )
        except SlackApiError as exc:
            logger.warning("Failed to add :eyes: reaction: %s", exc)

        analysis = await _run_analysis(
            trigger["model"],
            trigger.get("column"),
            client,
        )

        analysis["model"] = trigger["model"]
        analysis["intent"] = trigger["intent"]
        analysis["column"] = trigger.get("column")
        analysis["channel_id"] = channel_id
        analysis["message_ts"] = message_ts

        _ANALYSIS_CACHE[cache_key] = analysis
        _trim_cache()

        blocks = build_impact_card(analysis)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=message_ts,
            blocks=blocks,
            text=f"Impact analysis for {trigger['model']}",
        )

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


# ---- Analysis orchestration ----


async def _run_analysis(
    model: str,
    column: str | None,
    client,
) -> dict:
    """Run all analysis tasks in parallel via asyncio.gather.

    Uses ``asyncio.to_thread`` for synchronous service calls and
    named futures to avoid fragile index arithmetic.

    Args:
        model: The detected dbt model name.
        column: Optional column name extracted from the message.
        client: ``AsyncWebClient`` for Slack API calls.

    Returns:
        Dict with keys ``lineage``, ``migration_order``,
        ``column_lineage`` (optional), ``usage``, ``last_change``,
        ``tests``, ``stale_threads``, ``experts``.
    """
    futures: dict[str, asyncio.Future] = {
        "lineage": asyncio.to_thread(get_lineage, model, _MANIFEST_PATH),
        "migration_order": asyncio.to_thread(
            get_migration_order, model, _MANIFEST_PATH,
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
        *futures.values(), return_exceptions=True,
    )
    analysis: dict = dict(zip(futures.keys(), results))

    lineage = analysis.get("lineage", {})
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
    """Search Slack for past threads mentioning the model via RTS API.

    Uses ``assistant.search.context`` with a user token. Falls back
    gracefully to an empty list if the user token is not configured
    or the search fails.

    Args:
        model: The model name to search for.

    Returns:
        List of message dicts from ``results.messages``.
    """
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
    """Identify threads that predate the last schema change.

    Args:
        rts_results: List of message match dicts from RTS search.
        last_change_ts: ISO-8601 timestamp of the last schema change.

    Returns:
        List of stale thread dicts with ``ts``, ``channel``, and ``permalink``.
    """
    if not last_change_ts:
        return []

    try:
        threshold = datetime.fromisoformat(last_change_ts).replace(
            tzinfo=timezone.utc
        )
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
            stale.append({
                "ts": thread_ts,
                "channel": channel_id,
                "permalink": match.get("permalink", ""),
            })

    return stale


def _rank_experts(rts_results: list[dict]) -> list[str]:
    """Rank users by reply count in RTS search results.

    Args:
        rts_results: List of message match dicts from RTS search.

    Returns:
        List of up to 3 user IDs, ranked by reply frequency.
    """
    user_counts: Counter[str] = Counter()
    for match in rts_results:
        user = match.get("author_user_id", "")
        if user:
            user_counts[user] += 1

    top_users = [user for user, _ in user_counts.most_common(3)]
    return top_users


def _ts_to_datetime(ts: str) -> datetime:
    """Convert a Slack timestamp (e.g. '1687531200.123456') to datetime.

    Args:
        ts: Slack timestamp string.

    Returns:
        A timezone-aware UTC datetime.
    """
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


# ---- Action handlers ----


async def handle_start_cross_team_review(ack, body, client):
    """Handle the 'Start Cross-Team Review' button click.

    Creates a dedicated review channel, invites experts and the triggering
    user, posts a Block Kit summary in the original thread, and pins it
    in the new channel.
    """
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = _lookup_analysis(channel_id, message_ts)
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
    """Handle the 'Generate Migration Plan' button click.

    Posts a structured checklist as a Block Kit threaded reply built
    from migration order and test results.
    """
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = _lookup_analysis(channel_id, message_ts)

        if analysis is None:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=":warning: Analysis data is no longer available. Please trigger a new impact analysis.",
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
    """Handle the 'Mark as Outdated' button click.

    Posts a Block Kit outdated notice as a threaded reply within each
    stale thread and confirms in the original thread.
    """
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = _lookup_analysis(channel_id, message_ts)

        if analysis is None:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=":warning: Analysis data is no longer available. Please trigger a new impact analysis.",
            )
            return

        stale_threads = analysis.get("stale_threads", [])
        last_change = analysis.get("last_change", {})
        last_change_data = last_change.get("last_change", {}) or {}
        last_change_date = last_change_data.get(
            "changed_at", "unknown date"
        )

        current_permalink = await _get_message_permalink(
            client, channel_id, message_ts
        )

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
    """Handle the 'Annotate PR' button click.

    Opens a modal for collecting PR number and optional summary details.
    Context (model_name, impact_summary, repo, token) is stored in
    ``private_metadata`` and carried into the view_submission handler.
    """
    await ack()
    try:
        ctx = _parse_action_value(body)
        if ctx is None:
            return

        model = ctx["model"]
        channel_id = ctx["channel_id"]
        message_ts = ctx["message_ts"]
        analysis = _lookup_analysis(channel_id, message_ts)

        impact_summary = ""
        if analysis:
            impact_summary = build_markdown_summary(analysis)

        view = build_pr_modal(model)
        view["private_metadata"] = json.dumps({
            "model_name": model,
            "impact_summary": impact_summary,
            "repo": _GITHUB_REPO,
            "channel_id": channel_id,
            "message_ts": message_ts,
        })

        await client.views_open(
            trigger_id=body["trigger_id"],
            view=view,
        )

    except Exception:
        logger.exception("Error opening annotate PR modal")
        await _send_error(client, body)


async def handle_annotate_pr_submission(ack, body, client, view):
    """Handle the modal submission for Annotate PR.

    Extracts the PR number and optional custom summary, calls
    ``github_service.annotate_pr``, and posts a Block Kit
    confirmation in the original thread.
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
    repo = metadata.get("repo", _GITHUB_REPO)
    channel_id = metadata.get("channel_id", "")
    message_ts = metadata.get("message_ts", "")

    state = view.get("state", {}).get("values", {})

    pr_id = state.get("pr_number_block", {}).get(
        "pr_number_input", {}
    ).get("value", "").strip()

    if not pr_id:
        await ack({
            "response_action": "errors",
            "errors": {
                "pr_number_block": "PR number is required.",
            },
        })
        return

    custom_notes = state.get("custom_summary_block", {}).get(
        "custom_summary_input", {}
    ).get("value", "").strip()

    include_full = False
    checkbox_block = state.get("include_summary_block", {})
    selected = checkbox_block.get("include_summary_checkbox", {}).get(
        "selected_options", []
    )
    include_full = any(
        opt.get("value") == "include_full_summary" for opt in selected
    )

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
            pr_id, pr_url, model_name,
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
    """Extract context dict from a button action's ``value`` field.

    Args:
        body: The full Bolt action/block_actions payload.

    Returns:
        Parsed dict with ``model``, ``channel_id``, ``message_ts``,
        or ``None`` if parsing fails.
    """
    try:
        actions = body.get("actions", [{}])
        value = actions[0].get("value", "{}")
        return json.loads(value)
    except (json.JSONDecodeError, IndexError, KeyError):
        logger.warning("Failed to parse action value from body")
        return None


def _lookup_analysis(channel_id: str, message_ts: str) -> dict | None:
    """Retrieve cached analysis results for a message.

    Args:
        channel_id: Slack channel ID.
        message_ts: Slack message timestamp.

    Returns:
        The analysis dict, or ``None`` if not found.
    """
    return _ANALYSIS_CACHE.get((channel_id, message_ts))


async def _send_error(client, body: dict) -> None:
    """Send a generic error message to the user in the original thread.

    Args:
        client: ``AsyncWebClient``.
        body: The action payload.
    """
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


async def _get_message_permalink(
    client, channel_id: str, message_ts: str
) -> str | None:
    """Resolve a message permalink via chat.getPermalink.

    Args:
        client: ``AsyncWebClient``.
        channel_id: Slack channel ID.
        message_ts: Slack message timestamp.

    Returns:
        Permalink URL string, or ``None`` if the lookup fails.
    """
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
