import logging
import re

logger = logging.getLogger(__name__)

KNOWN_MODELS: frozenset[str] = frozenset({
    "fct_sales_pipeline",
    "fct_revenue_recognition",
    "rpt_commissions",
    "dim_customer",
    "stg_salesforce__opportunity",
    "stg_finance__revenue",
    "stg_customer",
})

INTENT_KEYWORDS: frozenset[str] = frozenset({
    "drop",
    "dropping",
    "remove",
    "removing",
    "deprecate",
    "deprecating",
    "rename",
    "renaming",
    "change",
    "changing",
    "refactor",
    "refactoring",
    "delete",
    "deleting",
    "modify",
    "modifying",
})


def detect_trigger(text: str) -> dict | None:
    """Scan message text for a model name paired with a change-intent keyword.

    Both a known model name and an intent keyword must be present in the
    text for a trigger to fire.  Optionally extracts a column name when
    the message mentions one near the model reference.

    Args:
        text: The plain-text body of a Slack channel message.

    Returns:
        ``{"model": str, "intent": str, "column": str | None}`` if a
        trigger is detected, or ``None`` if the message does not match.
    """
    text_lower = text.lower()

    matched_model = _extract_model(text_lower)
    if matched_model is None:
        return None

    matched_intent = _extract_intent(text_lower)
    if matched_intent is None:
        return None

    matched_column = _extract_column(text_lower, matched_model)

    logger.info(
        "Trigger detected: model=%s intent=%s column=%s",
        matched_model,
        matched_intent,
        matched_column,
    )
    return {
        "model": matched_model,
        "intent": matched_intent,
        "column": matched_column,
    }


def _extract_model(text_lower: str) -> str | None:
    for model in sorted(KNOWN_MODELS, key=len, reverse=True):
        if model in text_lower:
            return model
    return None


def _extract_intent(text_lower: str) -> str | None:
    for keyword in sorted(INTENT_KEYWORDS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower):
            return keyword
    return None


_intent_alt = "|".join(
    re.escape(kw) for kw in sorted(INTENT_KEYWORDS, key=len, reverse=True)
)
_COLUMN_PATTERN = re.compile(
    rf"(?:{_intent_alt})\s+"
    r"(?:the\s+)?"
    r"([a-z_]\w*)\s+"
    r"(?:column|field)?\s*"
    r"(?:from|in|of)\s+"
    r"\w[\w_]*",
    re.IGNORECASE,
)


_NON_COLUMN_WORDS: frozenset[str] = frozenset({"column", "field", "table", "model"})


def _extract_column(text_lower: str, model_name: str) -> str | None:
    match = _COLUMN_PATTERN.search(text_lower)
    if match is None:
        return None
    column = match.group(1)
    if column == model_name:
        return None
    if column in INTENT_KEYWORDS:
        return None
    if column in _NON_COLUMN_WORDS:
        return None
    return column
