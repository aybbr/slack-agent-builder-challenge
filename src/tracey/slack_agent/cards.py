import base64
import json
import logging

logger = logging.getLogger(__name__)

ACTION_IDS = {
    "start_cross_team_review": "start_cross_team_review",
    "generate_migration_plan": "generate_migration_plan",
    "mark_as_outdated": "mark_as_outdated",
    "annotate_pr": "annotate_pr",
    "close_pr": "close_pr",
}

ANNOTATE_PR_MODAL_CALLBACK = "annotate_pr_modal"
CLOSE_PR_MODAL_CALLBACK = "close_pr_modal"

_MODEL_NAME_LABEL = "model_name"
_IMPACT_SUMMARY_LABEL = "impact_summary"
_REPO_LABEL = "repo"
_TOKEN_LABEL = "token"


def build_impact_card(analysis: dict) -> list[dict]:
    """Build the main Block Kit impact card from aggregated analysis results.

    Args:
        analysis: Dict with keys ``model``, ``intent``, ``column``,
            ``lineage``, ``migration_order``, ``column_lineage``,
            ``usage``, ``last_change``, ``tests``, ``stale_threads``,
            ``experts``, ``channel_id``, ``message_ts``.

    Returns:
        A list of Slack Block Kit block dicts forming the impact card.
    """
    model = analysis["model"]
    column = analysis.get("column")
    intent = analysis["intent"]
    lineage = analysis.get("lineage", {})
    migration_order = analysis.get("migration_order", {})
    column_lineage = analysis.get("column_lineage")
    usage = analysis.get("usage", {})
    last_change = analysis.get("last_change", {})
    stale_threads = analysis.get("stale_threads", [])
    experts = analysis.get("experts", [])
    channel_id = analysis.get("channel_id", "")
    message_ts = analysis.get("message_ts", "")

    blocks: list[dict] = []

    blocks.append(_header_block(model, intent))

    _add_structural_impact(blocks, lineage, column_lineage, column)

    _add_usage_section(blocks, usage)

    _add_migration_preview(blocks, migration_order)

    _add_cross_team_awareness(blocks, experts, stale_threads, last_change)

    blocks.append(_actions_block(model, channel_id, message_ts))

    return blocks


def build_checklist_blocks(
    migration_order: list[dict],
    tests: list[dict],
    referential_tests: list[dict],
    model_name: str,
) -> list[dict]:
    """Build a migration checklist as Block Kit section blocks.

    Each migration step is a section block with an emoji status indicator.

    Args:
        migration_order: List of migration step dicts (from get_migration_order).
        tests: List of owned test dicts (from get_tests).
        referential_tests: List of referential test dicts.
        model_name: Name of the model being migrated.

    Returns:
        List of Slack Block Kit block dicts.
    """
    blocks: list[dict] = []

    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Migration Plan: {model_name}",
                "emoji": True,
            },
        }
    )

    test_status = _summarise_tests(tests, referential_tests)
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Test Status:* {test_status}",
            },
        }
    )

    if not migration_order:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":white_check_mark: No downstream models to migrate.",
                },
            }
        )
        return blocks

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Migration Steps:*"},
        }
    )

    for step in migration_order:
        step_id = step.get("id", "?")
        step_domain = step.get("domain", "unknown")
        is_source = step.get("is_source", False)
        cross_domain = step.get("cross_domain", False)

        icon = ":small_blue_diamond:" if is_source else ":arrow_forward:"
        tags = []
        if is_source:
            tags.append("`source`")
        if cross_domain:
            tags.append("`cross-domain`")

        tag_text = " " + " ".join(tags) if tags else ""
        text = f"{icon} *{step_id}* ({step_domain}){tag_text}"

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            }
        )

    return blocks


def build_stale_thread_block(
    thread_ts: str,
    thread_channel: str,
    thread_permalink: str,
    last_change_date: str,
    current_thread_url: str,
) -> list[dict]:
    """Build a Block Kit outdated notice for a single stale thread.

    Args:
        thread_ts: Timestamp of the stale thread's parent message.
        thread_channel: Channel ID where the stale thread lives.
        thread_permalink: Permalink URL to the stale thread.
        last_change_date: ISO-8601 date of the last schema change.
        current_thread_url: Permalink URL to the current discussion.

    Returns:
        List of Slack Block Kit block dicts.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":information_source: This discussion may be outdated. "
                    f"The model was last changed on *{last_change_date}*. "
                    f"See the <{current_thread_url}|current discussion> "
                    f"for the latest context."
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (f"Original thread: <{thread_permalink}|view in {thread_channel}>"),
                },
            ],
        },
    ]


def build_pr_modal(model_name: str, pr_number: str | None = None) -> dict:
    """Build a Slack modal view for collecting PR annotation details.

    Args:
        model_name: Name of the dbt model being annotated.
        pr_number: Optional PR number to pre-fill the input (from context).

    Returns:
        A Slack view payload dict suitable for ``views.open``.
    """
    pr_element: dict = {
        "type": "plain_text_input",
        "action_id": "pr_number_input",
        "placeholder": {"type": "plain_text", "text": "e.g. 42", "emoji": True},
    }
    if pr_number:
        pr_element["initial_value"] = pr_number

    return {
        "type": "modal",
        "callback_id": ANNOTATE_PR_MODAL_CALLBACK,
        "title": {"type": "plain_text", "text": "Annotate PR", "emoji": True},
        "submit": {"type": "plain_text", "text": "Annotate", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "input",
                "block_id": "pr_number_block",
                "element": pr_element,
                "label": {
                    "type": "plain_text",
                    "text": "Pull Request Number",
                    "emoji": True,
                },
            },
            {
                "type": "input",
                "block_id": "custom_summary_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "custom_summary_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Additional notes to append to the impact summary...",
                        "emoji": True,
                    },
                },
                "label": {
                    "type": "plain_text",
                    "text": "Custom Summary",
                    "emoji": True,
                },
            },
            {
                "type": "input",
                "block_id": "labels_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "labels_input",
                    "initial_value": "do not merge",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Comma-separated labels, e.g. do not merge, needs-review",
                        "emoji": True,
                    },
                },
                "label": {
                    "type": "plain_text",
                    "text": "Labels",
                    "emoji": True,
                },
            },
            {
                "type": "input",
                "block_id": "include_summary_block",
                "optional": True,
                "element": {
                    "type": "checkboxes",
                    "action_id": "include_summary_checkbox",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Include full impact summary",
                                "emoji": True,
                            },
                            "value": "include_full_summary",
                        },
                    ],
                    "initial_options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Include full impact summary",
                                "emoji": True,
                            },
                            "value": "include_full_summary",
                        },
                    ],
                },
                "label": {
                    "type": "plain_text",
                    "text": "Options",
                    "emoji": True,
                },
            },
        ],
        "private_metadata": json.dumps({_MODEL_NAME_LABEL: model_name}),
    }


def build_pr_confirmation_blocks(
    pr_id: str,
    pr_url: str | None,
    model_name: str,
) -> list[dict]:
    """Build a Block Kit confirmation posted after a successful PR annotation.

    Args:
        pr_id: The pull request number.
        pr_url: Full URL to the PR (from github_service.annotate_pr).
        model_name: Name of the annotated model.

    Returns:
        List of Slack Block Kit block dicts.
    """
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (f":white_check_mark: Impact analysis annotated on PR *{pr_id}* for `{model_name}`."),
            },
        },
    ]

    if pr_url:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{pr_url}|View PR #{pr_id}>",
                    },
                ],
            }
        )

    return blocks


def build_close_pr_modal(model_name: str, pr_number: str | None = None) -> dict:
    """Build a Slack modal view for closing a PR with an optional comment.

    The modal itself is the confirmation step for this destructive action —
    the user must click the red ``Close PR`` submit button.

    Args:
        model_name: Name of the dbt model discussed in the thread.
        pr_number: Optional PR number to pre-fill the input (from context).

    Returns:
        A Slack view payload dict suitable for ``views.open``.
    """
    pr_element: dict = {
        "type": "plain_text_input",
        "action_id": "pr_number_input",
        "placeholder": {"type": "plain_text", "text": "e.g. 42", "emoji": True},
    }
    if pr_number:
        pr_element["initial_value"] = pr_number

    return {
        "type": "modal",
        "callback_id": CLOSE_PR_MODAL_CALLBACK,
        "title": {"type": "plain_text", "text": "Close PR", "emoji": True},
        "submit": {"type": "plain_text", "text": "Close PR", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":warning: This will *close* the pull request for `{model_name}`. "
                        "The branch is preserved, so it can be reopened later."
                    ),
                },
            },
            {
                "type": "input",
                "block_id": "pr_number_block",
                "element": pr_element,
                "label": {
                    "type": "plain_text",
                    "text": "Pull Request Number",
                    "emoji": True,
                },
            },
            {
                "type": "input",
                "block_id": "close_comment_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "close_comment_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Optional reason for closing (posted as a PR comment)...",
                        "emoji": True,
                    },
                },
                "label": {
                    "type": "plain_text",
                    "text": "Closing Comment",
                    "emoji": True,
                },
            },
        ],
        "private_metadata": json.dumps({_MODEL_NAME_LABEL: model_name}),
    }


def build_pr_closed_confirmation_blocks(
    pr_id: str,
    pr_url: str | None,
    model_name: str,
) -> list[dict]:
    """Build a Block Kit confirmation posted after a PR is closed.

    Args:
        pr_id: The pull request number.
        pr_url: Full URL to the PR (from github_service.close_pr).
        model_name: Name of the model discussed in the thread.

    Returns:
        List of Slack Block Kit block dicts.
    """
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (f":lock: Closed PR *{pr_id}* for `{model_name}`. Reopen it if the team decides to proceed."),
            },
        },
    ]

    if pr_url:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{pr_url}|View PR #{pr_id}>",
                    },
                ],
            }
        )

    return blocks


def build_cross_team_summary_blocks(
    model_name: str,
    channel_name: str,
    experts: list[str],
    channel_url: str | None = None,
) -> list[dict]:
    """Build a Block Kit summary for the cross-team review thread reply.

    Args:
        model_name: The dbt model under review.
        channel_name: Name of the newly created review channel.
        experts: List of expert user IDs (for @mentions).
        channel_url: Optional Slack URL to the new channel.

    Returns:
        List of Slack Block Kit block dicts.
    """
    channel_ref = f"<#{channel_url}|{channel_name}>" if channel_url else f"#{channel_name}"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Cross-Team Review: {model_name}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (f"A cross-team review has been initiated for `{model_name}` in {channel_ref}."),
            },
        },
    ]

    if experts:
        mentions = ", ".join(f"<@{expert}>" for expert in experts)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Invited experts:* {mentions}",
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No experts identified. Invite relevant team members manually._",
                },
            }
        )

    return blocks


def build_marked_outdated_confirmation(count: int) -> list[dict]:
    """Build a Block Kit confirmation for marking stale threads as outdated.

    Args:
        count: Number of stale threads that were marked.

    Returns:
        List of Slack Block Kit block dicts.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":white_check_mark: Marked *{count}* stale thread(s) as outdated.",
            },
        },
    ]


def build_markdown_summary(analysis: dict) -> str:
    """Build a Markdown impact summary from analysis results.

    Used both by the impact card builder (inline) and as a standalone
    summary for PR annotations and other contexts.

    Args:
        analysis: The full analysis dict.

    Returns:
        A Markdown-formatted summary string.
    """
    model = analysis.get("model", "unknown")
    intent = analysis.get("intent", "change")
    column = analysis.get("column")

    lineage = analysis.get("lineage", {})
    downstream = lineage.get("downstream", [])

    usage = analysis.get("usage", {})
    total_queries = usage.get("total_queries", 0)
    total_dashboards = usage.get("total_dashboards", 0)

    lines = [
        f"## Impact Analysis: {model}",
        "",
        f"**Intent:** {intent}",
    ]

    if column:
        lines.append(f"**Column:** `{column}`")

    lines.append("")

    cross = [d for d in downstream if d.get("cross_domain")]
    same = [d for d in downstream if not d.get("cross_domain")]
    lines.append(f"- **Upstream:** {len(lineage.get('upstream', []))} model(s)")
    lines.append(f"- **Downstream:** {len(same)} same-domain, {len(cross)} cross-domain")
    lines.append(f"- **Usage:** {total_queries} queries, {total_dashboards} dashboards")

    if cross:
        lines.append("")
        lines.append("### Cross-Domain Impact")
        for d in cross:
            lines.append(f"- `{d['id']}` ({d.get('domain', '?')})")

    return "\n".join(lines)


def build_impact_header(
    model_name: str,
    downstream_count: int,
    cross_domain_count: int,
    domain: str = "",
) -> list[dict]:
    """Build a header and context block summarising impact scope."""
    stats: list[str] = []
    if downstream_count:
        stats.append(f"{downstream_count} downstream")
    if cross_domain_count:
        stats.append(f"{cross_domain_count} cross-domain :warning:")
    if domain:
        stats.insert(0, f"Domain: *{domain}*")

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Impact Analysis: {model_name}",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": " · ".join(stats) if stats else "_No downstream impact detected_",
                },
            ],
        },
    ]


def build_downstream_section(downstream: list[dict]) -> list[dict] | None:
    """Build section blocks listing downstream models with domain tags."""
    if not downstream:
        return None

    lines: list[str] = []
    for d in downstream:
        dom = d.get("domain", "?")
        cross = " :warning: cross-domain" if d.get("cross_domain") else ""
        lines.append(f"• `{d['id']}` ({dom}){cross}")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Downstream Models*\n" + "\n".join(lines)},
        },
    ]


def build_usage_section(usage: dict) -> list[dict] | None:
    """Build section blocks with per-domain usage statistics."""
    by_domain = usage.get("by_domain", [])
    total_queries = usage.get("total_queries", 0)
    total_dashboards = usage.get("total_dashboards", 0)

    if not total_queries and not total_dashboards:
        return None

    lines = [f"*Total:* {total_queries} queries/wk, {total_dashboards} dashboards"]
    for entry in by_domain:
        lines.append(f"• *{entry['domain']}:* {entry['queries']} queries, {entry['dashboards']} dashboards")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
    ]


def build_migration_preview_section(migration_order: dict) -> list[dict] | None:
    """Build a section previewing the first few migration steps."""
    steps = migration_order.get("migration_order", [])
    if not steps:
        return None

    preview = steps[:5]
    lines = ["*Migration Order (first 5):*"]
    for step in preview:
        order = step.get("order", "?")
        step_id = step.get("id", "?")
        cross = " :arrow_right: *cross-domain*" if step.get("cross_domain") else ""
        lines.append(f"  {order}. `{step_id}`{cross}")

    if len(steps) > 5:
        lines.append(f"  _... and {len(steps) - 5} more_")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
    ]


def build_cross_team_section(
    experts: list[str],
    stale_threads: list[dict],
    last_change: dict | None = None,
) -> list[dict]:
    """Build section blocks with cross-team awareness summary."""
    if not experts and not stale_threads:
        return None

    lines: list[str] = []
    if experts:
        mentions = ", ".join(f"<@{expert}>" for expert in experts[:3])
        lines.append(f"*Suggested experts:* {mentions}")
    if stale_threads:
        lines.append(f"*Past discussions:* {len(stale_threads)} found (may be outdated)")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
    ]


def build_feedback_blocks() -> list[dict]:
    """Build feedback buttons and disclaimer blocks."""
    return [
        {
            "type": "context_actions",
            "elements": [
                {
                    "type": "feedback_buttons",
                    "action_id": "tracey_feedback",
                    "positive_button": {
                        "text": {"type": "plain_text", "text": "👍"},
                        "value": "positive_feedback",
                    },
                    "negative_button": {
                        "text": {"type": "plain_text", "text": "👎"},
                        "value": "negative_feedback",
                    },
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":information_source: AI-generated analysis. Verify before acting.",
                },
            ],
        },
    ]


def build_review_modal(
    model_name: str,
    experts: list[str],
    channel_id: str,
    message_ts: str,
) -> dict:
    """Build a modal for configuring the cross-team review before creation."""
    initial_users = experts[:10] if experts else []

    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Set up a cross-team review channel for `{model_name}`.",
            },
        },
        {
            "type": "input",
            "block_id": "experts_block",
            "label": {"type": "plain_text", "text": "Experts to invite", "emoji": True},
            "element": {
                "type": "multi_users_select",
                "action_id": "experts_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select team members",
                    "emoji": True,
                },
                "initial_users": initial_users,
            },
        },
        {
            "type": "input",
            "block_id": "notes_block",
            "optional": True,
            "label": {"type": "plain_text", "text": "Notes (optional)", "emoji": True},
            "element": {
                "type": "plain_text_input",
                "action_id": "notes_input",
                "multiline": True,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Add context for the review team...",
                    "emoji": True,
                },
            },
        },
    ]

    from datetime import datetime

    suffix = datetime.now().strftime("%y%m%d%H%M")
    return {
        "type": "modal",
        "callback_id": "review_modal",
        "title": {"type": "plain_text", "text": "Start Review", "emoji": True},
        "submit": {"type": "plain_text", "text": "Create Channel", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": blocks,
        "private_metadata": json.dumps(
            {
                "model": model_name,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "suggested_name": f"review-{model_name}-{suffix}",
            }
        ),
    }


def build_outdated_modal(
    model_name: str,
    stale_threads: list[dict],
    last_change_date: str,
    channel_id: str,
    message_ts: str,
) -> dict:
    """Build a modal listing stale threads with checkboxes for selection."""
    if not stale_threads:
        return {
            "type": "modal",
            "callback_id": "outdated_modal",
            "title": {"type": "plain_text", "text": "No Stale Threads", "emoji": True},
            "close": {"type": "plain_text", "text": "Close", "emoji": True},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":white_check_mark: No outdated threads detected for `{model_name}`.",
                    },
                },
            ],
            "private_metadata": "{}",
        }

    options = []
    for i, thread in enumerate(stale_threads[:10]):
        permalink = thread.get("permalink", "")
        channel = thread.get("channel", "")
        label = f"#{channel}" if channel else f"Thread {i + 1}"
        if permalink:
            label += f" (<{permalink}|view>)"
        options.append(
            {
                "text": {"type": "mrkdwn", "text": label, "verbatim": False},
                "value": json.dumps({"ts": thread["ts"], "channel": thread["channel"]}),
            }
        )

    return {
        "type": "modal",
        "callback_id": "outdated_modal",
        "title": {"type": "plain_text", "text": "Mark as Outdated", "emoji": True},
        "submit": {"type": "plain_text", "text": "Mark Selected", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Select threads to mark as outdated for `{model_name}`. Last change: *{last_change_date}*"
                    ),
                },
            },
            {
                "type": "input",
                "block_id": "threads_block",
                "label": {
                    "type": "plain_text",
                    "text": f"{len(stale_threads)} stale thread(s) found",
                    "emoji": True,
                },
                "element": {
                    "type": "checkboxes",
                    "action_id": "threads_checkbox",
                    "options": options,
                    "initial_options": options,
                },
            },
        ],
        "private_metadata": json.dumps(
            {
                "model": model_name,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "last_change_date": last_change_date,
            }
        ),
    }


def build_migration_modal(
    model_name: str,
    migration_order: list[dict],
    channel_id: str,
    message_ts: str,
) -> dict:
    """Build a modal for confirming migration plan generation."""
    options = []
    for step in migration_order:
        step_id = step.get("id", "?")
        step_domain = step.get("domain", "?")
        is_source = step.get("is_source", False)
        cross = " ⚠️ cross-domain" if step.get("cross_domain") else ""
        label = f"`{step_id}` ({step_domain})" + (" — source" if is_source else "") + cross
        options.append(
            {
                "text": {"type": "mrkdwn", "text": label, "verbatim": False},
                "value": step_id,
            }
        )

    return {
        "type": "modal",
        "callback_id": "migration_modal",
        "title": {"type": "plain_text", "text": "Migration Plan", "emoji": True},
        "submit": {"type": "plain_text", "text": "Generate Plan", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Generate a migration checklist for `{model_name}`. Select the steps to include.",
                },
            },
            {
                "type": "input",
                "block_id": "steps_block",
                "label": {
                    "type": "plain_text",
                    "text": f"{len(migration_order)} migration step(s)",
                    "emoji": True,
                },
                "element": {
                    "type": "checkboxes",
                    "action_id": "steps_checkbox",
                    "options": options,
                    "initial_options": options,
                },
            },
            {
                "type": "input",
                "block_id": "notes_block",
                "optional": True,
                "label": {"type": "plain_text", "text": "Additional notes", "emoji": True},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Any special instructions for the migration...",
                        "emoji": True,
                    },
                },
            },
        ],
        "private_metadata": json.dumps(
            {
                "model": model_name,
                "channel_id": channel_id,
                "message_ts": message_ts,
            }
        ),
    }


# ---- Private helpers ----


def _header_block(model: str, intent: str) -> dict:
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Proposed change to {model}",
            "emoji": True,
        },
    }


def _add_structural_impact(
    blocks: list[dict],
    lineage: dict,
    column_lineage: dict | None,
    column: str | None,
) -> None:
    domain = lineage.get("domain", "unknown")
    upstream = lineage.get("upstream", [])
    downstream = lineage.get("downstream", [])

    lines = [
        f"*Domain:* {domain}",
        f"*Upstream:* {', '.join(u['id'] for u in upstream) if upstream else 'None'}",
    ]

    cross = [d for d in downstream if d.get("cross_domain")]
    same = [d for d in downstream if not d.get("cross_domain")]

    if cross:
        cross_names = ", ".join(f"`{d['id']}` ({d.get('domain', '?')})" for d in cross)
        lines.append(f"*Cross-domain downstream:* {cross_names}")
    if same:
        same_names = ", ".join(f"`{d['id']}`" for d in same)
        lines.append(f"*Same-domain downstream:* {same_names}")

    if column and column_lineage:
        usages = column_lineage.get("downstream_usages", [])
        if usages:
            models_using = {u["model"] for u in usages}
            lines.append(f"*Column `{column}` used in:* {', '.join(f'`{m}`' for m in sorted(models_using))}")
            high_conf = [u for u in usages if u.get("confidence") == "high"]
            if high_conf:
                types = {u.get("usage_type", "unknown") for u in high_conf}
                lines.append(f"*Usage types:* {', '.join(sorted(types))}")
        else:
            lines.append(f"*Column `{column}`:* No downstream usage detected")

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }
    )


def _add_usage_section(blocks: list[dict], usage: dict) -> None:
    by_domain = usage.get("by_domain", [])
    total_queries = usage.get("total_queries", 0)
    total_dashboards = usage.get("total_dashboards", 0)

    lines = [
        f"*Total:* {total_queries} queries, {total_dashboards} dashboards",
    ]
    for entry in by_domain:
        lines.append(f"• *{entry['domain']}:* {entry['queries']} queries, {entry['dashboards']} dashboards")

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }
    )


def _add_migration_preview(blocks: list[dict], migration_order: dict) -> None:
    steps = migration_order.get("migration_order", [])
    if not steps:
        return

    preview = steps[:5]
    lines = ["*Migration Order (first 5):*"]
    for step in preview:
        order = step.get("order", "?")
        step_id = step.get("id", "?")
        cross = " :arrow_right: *cross-domain*" if step.get("cross_domain") else ""
        lines.append(f"  {order}. `{step_id}`{cross}")

    if len(steps) > 5:
        lines.append(f"  _... and {len(steps) - 5} more_")

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }
    )


def _add_cross_team_awareness(
    blocks: list[dict],
    experts: list[str],
    stale_threads: list[dict],
    last_change: dict,
) -> None:
    lines: list[str] = []

    if experts:
        mentions = ", ".join(f"<@{expert}>" for expert in experts[:3])
        lines.append(f"*Suggested experts:* {mentions}")
    else:
        lines.append("*Suggested experts:* None identified")

    if stale_threads:
        lines.append(f"*Stale threads:* {len(stale_threads)} found (predate last change)")
    else:
        lines.append("*Stale threads:* None detected")

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }
    )


def _actions_block(
    model: str,
    channel_id: str,
    message_ts: str,
    visible: set[str] | None = None,
) -> dict | None:
    """Build the action buttons block, optionally gated by ``visible``.

    When ``visible`` is ``None``, all four buttons are rendered (backward-
    compatible fallback).  Otherwise only the buttons whose keys appear in
    ``visible`` are included.  Returns ``None`` when no buttons would be
    shown (empty ``visible`` set).

    Key mapping:
        ``"review"`` → Start Cross-Team Review
        ``"migration"`` → Generate Migration Plan
        ``"outdated"`` → Mark as Outdated
        ``"pr"`` → Annotate PR
        ``"close_pr"`` → Close PR
    """
    context = json.dumps(
        {
            "model": model,
            "channel_id": channel_id,
            "message_ts": message_ts,
        }
    )

    _ALL_BUTTONS = (
        ("review", "Start Cross-Team Review", ACTION_IDS["start_cross_team_review"], "primary"),
        ("migration", "Generate Migration Plan", ACTION_IDS["generate_migration_plan"], None),
        ("outdated", "Mark as Outdated", ACTION_IDS["mark_as_outdated"], None),
        ("pr", "Annotate PR", ACTION_IDS["annotate_pr"], "primary"),
        ("close_pr", "Close PR", ACTION_IDS["close_pr"], "danger"),
    )

    elements: list[dict] = []
    for key, label, action_id, style in _ALL_BUTTONS:
        if visible is not None and key not in visible:
            continue
        btn: dict = {
            "type": "button",
            "text": {"type": "plain_text", "text": label, "emoji": True},
            "action_id": action_id,
            "value": context,
        }
        if style:
            btn["style"] = style
        elements.append(btn)

    if not elements:
        return None

    return {
        "type": "actions",
        "block_id": "impact_actions",
        "elements": elements,
    }


_MERMAID_INK_BASE = "https://mermaid.ink/img"


async def _render_mermaid_to_slack(
    mermaid_syntax: str,
    title: str,
    channel_id: str,
    thread_ts: str,
    client,
) -> str | None:
    """Render Mermaid syntax to PNG via mermaid.ink and upload to Slack.

    Returns the file permalink on success, ``None`` on failure.
    Can raise ``aiohttp.ClientError``, ``SlackApiError``.
    """
    import aiohttp
    from slack_sdk.errors import SlackApiError as _SlackApiError

    encoded = base64.urlsafe_b64encode(mermaid_syntax.encode()).decode().rstrip("=")
    mermaid_url = f"{_MERMAID_INK_BASE}/{encoded}"

    async with aiohttp.ClientSession() as session:
        resp = await session.get(mermaid_url)
        try:
            if resp.status != 200:
                logger.warning("mermaid.ink returned HTTP %d", resp.status)
                return None
            image_bytes = await resp.read()
        finally:
            resp.close()

    try:
        upload_result = await client.files_upload_v2(
            channel=channel_id,
            thread_ts=thread_ts,
            file=image_bytes,
            filename=f"migration_{thread_ts}.png",
            title=title,
        )
    except _SlackApiError:
        logger.exception("Slack file upload failed for migration diagram")
        return None

    files = upload_result.get("files", [])
    return files[0].get("permalink", "") if files else None


def build_migration_diagram_syntax(
    model: str,
    migration_order: list[dict],
    lineage: dict,
) -> str:
    """Build Mermaid ``flowchart LR`` syntax for a topologically sorted migration.

    The source model is highlighted; downstream nodes are numbered with their
    migration step.  Cross-domain nodes get an orange colour and ⚠️ marker.
    """
    downstream: list = lineage.get("downstream", [])
    source_domain = lineage.get("domain", "")
    domain_map: dict[str, str] = {d.get("name", ""): d.get("domain", "") for d in downstream}
    domain_map[model] = source_domain

    order_map: dict[str, int] = {}
    for step in migration_order:
        name = step.get("id", "") if isinstance(step, dict) else str(step)
        order_map[name] = step.get("order", 99) if isinstance(step, dict) else 99

    sorted_models = sorted(order_map.items(), key=lambda x: (x[1], x[0]))
    sorted_names = [m for m, _ in sorted_models if m != model]
    if model not in order_map:
        sorted_names.insert(0, model)

    def _node_id(name: str) -> str:
        return name.replace("-", "_").replace(".", "_")

    def _label(name: str) -> str:
        domain = domain_map.get(name, "")
        step = order_map.get(name, "")
        step_str = f"Step {step}: " if step else ""
        extra = f"\\n{domain}" if domain else ""
        cross = " ⚠️" if domain and domain != source_domain else ""
        return f'["`{step_str}**{name}**{cross}{extra}`"]'

    lines = ["flowchart LR"]
    for name in sorted_names:
        nid = _node_id(name)
        domain = domain_map.get(name, "")
        if name == model:
            style = "fill:#a5d8ff,stroke:#4a9eed,stroke-width:3px"
        elif domain != source_domain:
            style = "fill:#ffd8a8,stroke:#f59e0b"
        else:
            style = "fill:#b2f2bb,stroke:#22c55e"
        lines.append(f"    style {nid} {style}")

    for name in sorted_names:
        nid = _node_id(name)
        lines.append(f"    {nid}{_label(name)}")

    for i in range(len(sorted_names) - 1):
        lines.append(f"    {_node_id(sorted_names[i])} --> {_node_id(sorted_names[i + 1])}")

    return "\n".join(lines)


def _summarise_tests(
    tests: list[dict],
    referential_tests: list[dict],
) -> str:
    total = len(tests) + len(referential_tests)
    errors = sum(1 for t in list(tests) + list(referential_tests) if t.get("severity") == "error")
    warns = sum(1 for t in list(tests) + list(referential_tests) if t.get("severity") == "warn")

    parts = [f"{total} test(s)"]
    if errors:
        parts.append(f"{errors} error(s)")
    if warns:
        parts.append(f"{warns} warning(s)")

    result = ", ".join(parts)

    if referential_tests:
        ref_models = {t.get("owner", "?") for t in referential_tests}
        result += f" (includes {len(referential_tests)} referential test(s) owned by {', '.join(sorted(ref_models))})"

    return result


_TOOL_DISPLAY_NAMES: dict[str, str] = {
    "mcp__dbt__get_lineage_dev": "Tracing dbt lineage",
    "mcp__dbt__get_node_details_dev": "Loading model details",
    "mcp__dbt__get_all_models": "Listing dbt models",
    "mcp__dbt__get_model_health": "Checking model health",
    "mcp__dbt__get_column_lineage": "Tracing column lineage",
    "mcp__tracey-tools__get_migration_order": "Computing migration order",
    "mcp__tracey-tools__get_usage": "Gathering usage stats",
    "mcp__tracey-tools__get_last_change": "Checking last change",
    "mcp__tracey-tools__search_slack_threads": "Searching Slack discussions",
    "mcp__tracey-tools__render_diagram_to_slack": "Rendering lineage diagram",
    "mcp__tracey-tools__annotate_pr": "Annotating pull request",
    "mcp__tracey-tools__close_pr": "Closing pull request",
    "mcp__tracey-tools__add_reaction": "Adding reaction",
    "mcp__mermaid__validate_and_render_mermaid_diagram": "Validating diagram syntax",
    "mcp__mermaid__get_diagram_title": "Generating diagram title",
    "mcp__mermaid__get_diagram_summary": "Summarising diagram",
}


def _friendly_tool_name(tool_name: str) -> str:
    """Map an MCP-namespaced tool name to a short display label."""
    return _TOOL_DISPLAY_NAMES.get(tool_name, tool_name.rsplit("__", 1)[-1].replace("_", " ").title())


def build_plan_block(tasks: list[dict]) -> dict:
    """Build a Slack plan block showing the agent's task progress.

    Args:
        tasks: List of dicts with keys ``task_id`` (str), ``name`` (str),
            ``status`` (str — ``in_progress``, ``complete``, or ``error``),
            and optional ``error`` (str).

    Returns:
        A ``"type": "plan"`` Block Kit block dict.
    """
    task_cards: list[dict] = []
    for t in tasks:
        card: dict = {
            "type": "task_card",
            "task_id": t["task_id"],
            "title": _friendly_tool_name(t["name"]),
            "status": t["status"],
        }
        if t["status"] == "error":
            card["details"] = {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": t.get("error", "Tool execution failed")}],
                    }
                ],
            }
        if t["status"] == "complete":
            card["output"] = {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "Done"}],
                    }
                ],
            }
        task_cards.append(card)

    return {
        "type": "plan",
        "title": "Agent thinking steps",
        "tasks": task_cards,
    }
