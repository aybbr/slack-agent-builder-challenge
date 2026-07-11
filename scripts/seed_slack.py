"""Slack workspace seeding script for Tracey demo.

Creates channels, posts realistic threaded conversations with distinct
persona display names and avatars, and updates the DuckDB changelog so
that stale-thread detection exercises the full agent pipeline.

Usage:
    uv run python scripts/seed_slack.py

Requires:
    SLACK_BOT_TOKEN in .env — bot token with chat:write.customize, channels:join, channels:manage
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = str(_DATA_DIR / "demo.duckdb")

_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

if not _BOT_TOKEN:
    logger.error("SLACK_BOT_TOKEN is required but not set")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Personas  (distinct display names + avatars)
# ---------------------------------------------------------------------------

PERSONAS: dict[str, tuple[str, str]] = {
    "alex": ("Alex Chen", ":male-technologist:"),
    "maya": ("Maya Patel", ":female-office-worker:"),
    "sam": ("Sam Rodriguez", ":male-astronaut:"),
    "jordan": ("Jordan Lee", ":female-genie:"),
    "taylor": ("Taylor Kim", ":technologist:"),
    "priya": ("Priya Shah", ":female-executive:"),
}

# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

CHANNELS = [
    "sales-data",
    "finance-data",
    "product-data",
    "data-ops",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_msg(
    client: WebClient,
    channel: str,
    text: str,
    persona: str,
    thread_ts: str | None = None,
) -> str:
    """Post a message as a persona and return its ts."""
    username, icon = PERSONAS[persona]
    try:
        resp = client.chat_postMessage(
            channel=channel,
            text=text,
            username=username,
            icon_emoji=icon,
            thread_ts=thread_ts,
        )
        return resp["ts"]
    except SlackApiError as exc:
        logger.error("Failed to post as %s in %s: %s", persona, channel, exc)
        raise


def _create_channel(client: WebClient, name: str) -> str:
    """Create a channel (idempotent — skips name_taken). Returns channel ID."""
    try:
        resp = client.conversations_create(name=name, is_private=False)
        channel_id = resp["channel"]["id"]
        logger.info("Created channel #%s -> %s", name, channel_id)
        return channel_id
    except SlackApiError as exc:
        if "name_taken" in str(exc):
            logger.info("Channel #%s already exists, looking up...", name)
            for ch in client.conversations_list(types="public_channel", limit=200):
                for c in ch.get("channels", []):
                    if c["name"] == name:
                        logger.info("Found existing #%s -> %s", name, c["id"])
                        return c["id"]
        raise


def _update_changelog_between(threshold_ts: str) -> None:
    """Set last_change for fct_sales_pipeline to threshold_ts so older threads appear stale."""
    threshold_dt = datetime.fromtimestamp(float(threshold_ts), tz=UTC)
    threshold_iso = threshold_dt.strftime("%Y-%m-%d %H:%M:%S")

    with duckdb.connect(_DB_PATH) as con:
        con.execute(
            """
            INSERT INTO schema_changelog VALUES
                (?, ?, 'refactor', 'alex.chen', 'Seeded changelog gate for stale-thread detection')
        """,
            ("fct_sales_pipeline", threshold_iso),
        )

    logger.info("Updated fct_sales_pipeline last_change to %s (gate between batches)", threshold_iso)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    client = WebClient(token=_BOT_TOKEN)
    channel_ids: dict[str, str] = {}

    # -- Step 1: Create channels -------------------------------------------------

    for ch in CHANNELS:
        channel_ids[ch] = _create_channel(client, ch)

    # -- Step 1b: Ensure bot is in every channel ---------------------------------

    for ch, cid in channel_ids.items():
        try:
            client.conversations_join(channel=cid)
            logger.info("Joined #%s", ch)
        except SlackApiError as exc:
            if "already_in_channel" not in str(exc) and "method_not_supported_for_channel_type" not in str(exc):
                logger.warning("Could not join #%s: %s", ch, exc)

    # -- Step 2: Set channel topics ---------------------------------------------

    topics = {
        "sales-data": "Sales pipeline, opportunity data, and dbt models. Ask questions anytime.",
        "finance-data": "Revenue recognition, billing, commissions, and forecasting.",
        "product-data": "Product analytics, feature adoption, and engagement metrics.",
        "data-ops": "Cross-team data operations, model lineage, platform infra.",
    }
    for ch, topic in topics.items():
        with suppress(SlackApiError):
            client.conversations_setTopic(channel=channel_ids[ch], topic=topic)

    # -- Step 3: Batch 1 — OLD threads (will become STALE) ----------------------

    logger.info("Posting Batch 1 (old threads)...")
    sid = channel_ids

    # T1: #sales-data — Commission confusion
    t1_ts = _post_msg(
        client,
        sid["sales-data"],
        "Hey team, my commission dashboard is showing weird numbers this week. "
        "The rates for enterprise accounts seem lower than last month. Anyone know what changed?",
        "priya",
    )
    _post_msg(
        client,
        sid["sales-data"],
        "Which accounts specifically? The commission model uses `lead_score` from "
        "`fct_sales_pipeline` to set rates — 12% for high scores, 8% for medium, "
        "5% for low. If an account's score dropped, the rate drops with it.",
        "alex",
        thread_ts=t1_ts,
    )
    _post_msg(
        client,
        sid["sales-data"],
        "That might be it. Where does `lead_score` actually come from? I want to "
        "understand what factors into it.",
        "priya",
        thread_ts=t1_ts,
    )
    _post_msg(
        client,
        sid["sales-data"],
        "It originates in our Salesforce opportunities table, gets averaged per "
        "account in `int_account_score`, then pulled into `int_account_360` along "
        "with product usage data, and finally into `fct_sales_pipeline`. A few "
        "layers deep. But the takeaway is your commission rate traces all the way "
        "back to a single column in staging.",
        "alex",
        thread_ts=t1_ts,
    )
    logger.info("  T1 posted — %s", t1_ts)

    # T2: #finance-data — Forecast surprise
    t2_ts = _post_msg(
        client,
        sid["finance-data"],
        "Our Q3 forecast dropped about 15 percent for top accounts overnight. "
        "I'm looking at `rpt_exec_dashboard` and the numbers just changed. "
        "Anyone touched anything upstream?",
        "maya",
    )
    _post_msg(
        client,
        sid["finance-data"],
        "Let me trace it. The dashboard pulls from `fct_revenue`, which uses "
        "a column called `lead_score_tier` from `fct_sales_pipeline` — that's "
        "owned by Sales. If someone adjusted the tiering logic upstream, it "
        "would cascade through.",
        "taylor",
        thread_ts=t2_ts,
    )
    _post_msg(
        client,
        sid["finance-data"],
        "Wait, that column is owned by Sales? So a Sales change broke my "
        "Finance forecast and nobody told us?",
        "maya",
        thread_ts=t2_ts,
    )
    _post_msg(
        client,
        sid["finance-data"],
        "Yeah it's a cross-domain thing. `int_pipeline_enrichment` which is "
        "sales gets joined into `fct_revenue` which is finance. Four levels "
        "deep from the column's origin in `stg_sf_opportunities`. Most people "
        "don't realise Finance depends on Sales staging data.",
        "taylor",
        thread_ts=t2_ts,
    )
    _post_msg(
        client,
        sid["finance-data"],
        "We need to flag this dependency somewhere. If Sales ever deprecates "
        "`lead_score`, our forecasts are dead. Let's make sure Tracey is "
        "watching the channels for this kind of thing.",
        "maya",
        thread_ts=t2_ts,
    )
    logger.info("  T2 posted — %s", t2_ts)

    # T3: #data-ops — Shared dependency concern
    t3_ts = _post_msg(
        client,
        sid["data-ops"],
        "Random observation: `stg_sf_accounts` is pulled by both sales models "
        "and product models. `int_account_score` and `int_product_usage` both "
        "depend on it. If someone changes the accounts source table, the blast "
        "radius is bigger than it looks.",
        "sam",
    )
    _post_msg(
        client,
        sid["data-ops"],
        "Already hit this last month. Renamed a column in accounts and it broke "
        "`int_product_usage`, which broke `int_account_360`, which broke "
        "`dim_account`. Took me three hours to trace it all the way down. "
        "Everything converges at that 360 model.",
        "jordan",
        thread_ts=t3_ts,
    )
    _post_msg(
        client,
        sid["data-ops"],
        "Same pattern with `fct_revenue` — it depends on `int_pipeline_enrichment` "
        "which depends on `int_account_360`. Finance models sitting on top of "
        "sales intermediates and most people don't realize until something breaks.",
        "alex",
        thread_ts=t3_ts,
    )
    logger.info("  T3 posted — %s", t3_ts)

    # T4: #product-data — New analyst needs help
    t4_ts = _post_msg(
        client,
        sid["product-data"],
        "Building a product adoption dashboard and I need account industry and "
        "region for segmentation. Which table has that?",
        "jordan",
    )
    _post_msg(
        client,
        sid["product-data"],
        "`stg_sf_accounts` — just a heads up it's owned by the Sales team. "
        "If they change the schema, your product models break. Happened to "
        "me a couple of times already.",
        "taylor",
        thread_ts=t4_ts,
    )
    _post_msg(
        client,
        sid["product-data"],
        "Makes sense thanks. So the full chain is `stg_sf_accounts` to "
        "`int_product_usage` to `int_account_360`? Just making sure I am "
        "joining the right things.",
        "jordan",
        thread_ts=t4_ts,
    )
    _post_msg(
        client,
        sid["product-data"],
        "Exactly. And `int_account_360` goes into `int_pipeline_enrichment` "
        "which feeds `fct_sales_pipeline`. So your product usage data actually "
        "flows into Sales pipeline models too. Goes both ways which is why "
        "coordination matters.",
        "taylor",
        thread_ts=t4_ts,
    )
    logger.info("  T4 posted — %s", t4_ts)

    # EDGE: Non-trigger — factual question
    _post_msg(
        client,
        sid["sales-data"],
        "What does `fct_sales_pipeline` do exactly? I am new here and trying "
        "to understand what models we have before building my dashboard.",
        "priya",
    )
    logger.info("  Edge (non-trigger question) posted")

    # EDGE: Negated — "should not touch"
    _post_msg(
        client,
        sid["data-ops"],
        "We should not touch the `lead_score` column until the new ML pipeline "
        "is validated end to end. Too many downstream things depend on it to "
        "rush a change like this.",
        "taylor",
    )
    logger.info("  Edge (negated) posted")

    # -- Step 4: Update changelog gate (3s wait between batches) ----------------

    logger.info("Waiting 3s for timestamp gap...")
    time.sleep(3)
    gap_ts = str(time.time())
    _update_changelog_between(gap_ts)

    # -- Step 5: Batch 2 — RECENT threads (NOT stale) --------------------------

    logger.info("Posting Batch 2 (recent threads)...")

    # T5: #finance-data — Board meeting prep (+ SQL DDL edge case)
    t5_ts = _post_msg(
        client,
        sid["finance-data"],
        "Prepping for the Q3 board meeting and I need forecasted vs actual "
        "revenue by account segment. Which model should I pull from and what "
        "column defines the segments?",
        "priya",
    )
    _post_msg(
        client,
        sid["finance-data"],
        "Use `rpt_exec_dashboard` — it combines actual revenue from `fct_revenue` "
        "with forecast data from `int_forecast_input`. The segment column is "
        "`lead_score_tier` which buckets accounts into high, medium, or low.",
        "maya",
        thread_ts=t5_ts,
    )
    _post_msg(
        client,
        sid["finance-data"],
        "Where does that tier come from? I see 'high', 'medium', 'low'.",
        "priya",
        thread_ts=t5_ts,
    )
    _post_msg(
        client,
        sid["finance-data"],
        "Originates from `fct_sales_pipeline`. It classifies accounts based on "
        "their lead score. If someone changes that column, your board materials "
        "change too. I will flag this so we are not surprised at the meeting.",
        "maya",
        thread_ts=t5_ts,
    )
    # SQL DDL edge case (reply in T5)
    _post_msg(
        client,
        sid["finance-data"],
        "Also I just saw this in a draft PR: `ALTER TABLE stg_sf_opportunities "
        "DROP COLUMN lead_score`. Does anyone know if this is actually happening? "
        "Because that would cascade through everything we just discussed.",
        "maya",
        thread_ts=t5_ts,
    )
    logger.info("  T5 posted — %s", t5_ts)

    # T6: #data-ops — Migration order question
    t6_ts = _post_msg(
        client,
        sid["data-ops"],
        "Quick sanity check — if we need to rebuild the DAG, what order do "
        "the models need to run? I know `int_account_360` needs both "
        "`int_account_score` and `int_product_usage` done first.",
        "taylor",
    )
    _post_msg(
        client,
        sid["data-ops"],
        "Yeah the order matters a lot because of those shared deps. "
        "`fct_revenue` needs `int_pipeline_enrichment` ready before it can "
        "compute the adjusted revenue column. If you run them alphabetically "
        "it fails because the child runs before its parent.",
        "jordan",
        thread_ts=t6_ts,
    )
    _post_msg(
        client,
        sid["data-ops"],
        "For `fct_sales_pipeline` the downstream chain is maybe five models "
        "deep? `rpt_commissions` depends on both `fct_sales_pipeline` and "
        "`fct_revenue`. Someone should automate this instead of everyone "
        "keeping a mental note of what depends on what.",
        "sam",
        thread_ts=t6_ts,
    )
    logger.info("  T6 posted — %s", t6_ts)

    # T7: #sales-data — THE DEMO TRIGGER
    t7_ts = _post_msg(
        client,
        sid["sales-data"],
        "Team update: we are deprecating the `lead_score` column in "
        "`fct_sales_pipeline` next sprint and replacing it with an ML "
        "based `model_score`. This affects commissions, revenue forecasts, "
        "and the exec dashboard — basically everything downstream of the "
        "pipeline. Let's make sure finance and product are in the loop "
        "before we cut over.",
        "alex",
    )
    logger.info("  T7 (trigger) posted — %s", t7_ts)

    # -- Step 6: Summary --------------------------------------------------------

    logger.info("=" * 60)
    logger.info("Slack workspace seeding complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Channel IDs (add to .env):")
    for ch, cid in channel_ids.items():
        logger.info("  #%s -> %s", ch, cid)
    logger.info("")
    logger.info("SLACK_TARGET_CHANNEL_IDS=%s", ",".join(channel_ids.values()))
    logger.info("")
    logger.info("Threads posted:")
    logger.info("  BATCH 1 (stale — predate last_change):")
    logger.info("    T1  #sales-data    Commission confusion")
    logger.info("    T2  #finance-data  Forecast surprise (cross-domain)")
    logger.info("    T3  #data-ops      Shared dependency concern")
    logger.info("    T4  #product-data  New analyst needs help")
    logger.info("    Edge #sales-data   Non-trigger: 'What does X do?'")
    logger.info("    Edge #data-ops     Negated: 'We should not touch X'")
    logger.info("  BATCH 2 (current — after last_change):")
    logger.info("    T5  #finance-data  Board meeting prep + SQL DDL")
    logger.info("    T6  #data-ops      Migration order question")
    logger.info("    T7  #sales-data    DEMO TRIGGER: deprecation notice")
    logger.info("")
    logger.info("Last change gate set at ts=%s", gap_ts)
    logger.info("")
    logger.info("Expected expert ranking: Taylor (4), Maya (4), Jordan (3)")
    logger.info("Expected stale threads: T1+T2+T3+T4 (predate changelog gate)")

    # -- Step 7: Write seeded analysis JSON ------------------------------------

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    seeded_analysis = {
        "fct_sales_pipeline": {
            "expert_names": ["Taylor Kim", "Maya Patel", "Jordan Lee"],
            "stale_threads": [
                {"ts": t1_ts, "channel": sid["sales-data"], "permalink": ""},
                {"ts": t2_ts, "channel": sid["finance-data"], "permalink": ""},
                {"ts": t3_ts, "channel": sid["data-ops"], "permalink": ""},
                {"ts": t4_ts, "channel": sid["product-data"], "permalink": ""},
            ],
            "last_change_date": datetime.fromtimestamp(float(gap_ts), tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
    }
    analysis_path = _DATA_DIR / "seeded_analysis.json"
    analysis_path.write_text(json.dumps(seeded_analysis, indent=2))
    logger.info("Wrote seeded analysis to %s", analysis_path)


if __name__ == "__main__":
    main()
