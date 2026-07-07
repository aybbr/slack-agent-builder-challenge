"""Deterministic model-name detection from dbt manifest.

Runs as a cheap pre-filter before invoking the LLM agent. Returns the first
model name found in the message text, or None. Uses word-boundary matching
to avoid partial matches. Loads model names from the dbt manifest at import
time — no hardcoded list.
"""

import logging
import os
import re
from functools import lru_cache

from tracey.services._manifest_helpers import _load_manifest

logger = logging.getLogger(__name__)

_MANIFEST_PATH = os.environ.get("MANIFEST_PATH", "dbt_project/target/manifest.json")


@lru_cache(maxsize=1)
def _get_model_names() -> frozenset[str]:
    """Load all model names from the dbt manifest.

    Returns:
        Frozen set of model names discovered from manifest nodes.
    """
    nodes = _load_manifest(_MANIFEST_PATH)
    return frozenset(
        node["name"]
        for uid, node in nodes.items()
        if uid.startswith("model.")
    )


def has_model_mention(text: str) -> str | None:
    """Return the first model name found in text, or None.

    Uses word-boundary matching to avoid partial matches (e.g. ``stg_customer``
    won't match inside ``stg_customer_report``). Models are checked longest-first
    to ensure the most specific match wins.

    Args:
        text: The plain-text body of a Slack channel message.

    Returns:
        The matched model name, or ``None`` if no model is mentioned.
    """
    text_lower = text.lower()
    for model in sorted(_get_model_names(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(model) + r"\b", text_lower):
            return model
    return None
