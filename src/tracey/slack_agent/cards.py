import json
import logging

logger = logging.getLogger(__name__)

ACTION_IDS = {
    "start_cross_team_review": "start_cross_team_review",
    "generate_migration_plan": "generate_migration_plan",
    "mark_as_outdated": "mark_as_outdated",
    "annotate_pr": "annotate_pr",
}

ANNOTATE_PR_MODAL_CALLBACK = "annotate_pr_modal"

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
    tests_result = analysis.get("tests", {})
    stale_threads = analysis.get("stale_threads", [])
    experts = analysis.get("experts", [])
    channel_id = analysis.get("channel_id", "")
    message_ts = analysis.get("message_ts", "")

    blocks: list[dict] = []

    blocks.append(_header_block(model, intent))

    _add_structural_impact(blocks, lineage, column_lineage, column)

    _add_usage_section(blocks, usage)

    _add_migration_preview(blocks, migration_order)

    _add_social_impact(blocks, experts, stale_threads, last_change)

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

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Migration Plan: {model_name}",
            "emoji": True,
        },
    })

    test_status = _summarise_tests(tests, referential_tests)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Test Status:* {test_status}",
        },
    })

    if not migration_order:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":white_check_mark: No downstream models to migrate.",
            },
        })
        return blocks

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Migration Steps:*"},
    })

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

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })

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
                    "text": (
                        f"Original thread: <{thread_permalink}|"
                        f"view in {thread_channel}>"
                    ),
                },
            ],
        },
    ]


def build_pr_modal(model_name: str) -> dict:
    """Build a Slack modal view for collecting PR annotation details.

    Args:
        model_name: Name of the dbt model being annotated.

    Returns:
        A Slack view payload dict suitable for ``views.open``.
    """
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
                "element": {
                    "type": "plain_text_input",
                    "action_id": "pr_number_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. 42",
                        "emoji": True,
                    },
                },
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
                    "text": "Custom Summary (optional)",
                    "emoji": True,
                },
            },
            {
                "type": "input",
                "block_id": "include_summary_block",
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
                "text": (
                    f":white_check_mark: Impact analysis annotated on "
                    f"PR *{pr_id}* for `{model_name}`."
                ),
            },
        },
    ]

    if pr_url:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"<{pr_url}|View PR #{pr_id}>",
                },
            ],
        })

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
                "text": (
                    f"A cross-team review has been initiated for "
                    f"`{model_name}` in {channel_ref}."
                ),
            },
        },
    ]

    if experts:
        mentions = ", ".join(f"<@{expert}>" for expert in experts)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Invited experts:* {mentions}",
            },
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_No experts identified. Invite relevant team members manually._",
            },
        })

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
            lines.append(
                f"*Column `{column}` used in:* "
                f"{', '.join(f'`{m}`' for m in sorted(models_using))}"
            )
            high_conf = [u for u in usages if u.get("confidence") == "high"]
            if high_conf:
                types = {u.get("usage_type", "unknown") for u in high_conf}
                lines.append(
                    f"*Usage types:* {', '.join(sorted(types))}"
                )
        else:
            lines.append(f"*Column `{column}`:* No downstream usage detected")

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    })


def _add_usage_section(blocks: list[dict], usage: dict) -> None:
    by_domain = usage.get("by_domain", [])
    total_queries = usage.get("total_queries", 0)
    total_dashboards = usage.get("total_dashboards", 0)

    lines = [
        f"*Total:* {total_queries} queries, {total_dashboards} dashboards",
    ]
    for entry in by_domain:
        lines.append(
            f"• *{entry['domain']}:* {entry['queries']} queries, "
            f"{entry['dashboards']} dashboards"
        )

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    })


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

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    })


def _add_social_impact(
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

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    })


def _actions_block(
    model: str,
    channel_id: str,
    message_ts: str,
) -> dict:
    context = json.dumps({
        "model": model,
        "channel_id": channel_id,
        "message_ts": message_ts,
    })

    return {
        "type": "actions",
        "block_id": "impact_actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Start Cross-Team Review",
                    "emoji": True,
                },
                "style": "primary",
                "action_id": ACTION_IDS["start_cross_team_review"],
                "value": context,
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Generate Migration Plan",
                    "emoji": True,
                },
                "action_id": ACTION_IDS["generate_migration_plan"],
                "value": context,
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Mark as Outdated",
                    "emoji": True,
                },
                "action_id": ACTION_IDS["mark_as_outdated"],
                "value": context,
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Annotate PR",
                    "emoji": True,
                },
                "style": "primary",
                "action_id": ACTION_IDS["annotate_pr"],
                "value": context,
            },
        ],
    }


def _summarise_tests(
    tests: list[dict],
    referential_tests: list[dict],
) -> str:
    total = len(tests) + len(referential_tests)
    errors = sum(
        1 for t in list(tests) + list(referential_tests)
        if t.get("severity") == "error"
    )
    warns = sum(
        1 for t in list(tests) + list(referential_tests)
        if t.get("severity") == "warn"
    )

    parts = [f"{total} test(s)"]
    if errors:
        parts.append(f"{errors} error(s)")
    if warns:
        parts.append(f"{warns} warning(s)")

    result = ", ".join(parts)

    if referential_tests:
        ref_models = {t.get("owner", "?") for t in referential_tests}
        result += (
            f" (includes {len(referential_tests)} referential test(s) "
            f"owned by {', '.join(sorted(ref_models))})"
        )

    return result
