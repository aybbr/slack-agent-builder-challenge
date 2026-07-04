import logging

from tracey.services._manifest_helpers import (
    _load_manifest,
    _resolve_asset_id,
)
from tracey.utils.errors import error_response

logger = logging.getLogger(__name__)


def get_tests(asset_id: str, manifest_path: str) -> dict:
    """Return all dbt tests that belong to a given model.

    Scans the manifest for test nodes whose ``attached_node`` matches the
    resolved asset (falling back to ``depends_on.nodes`` for manifests that
    lack ``attached_node``). Uses manifest metadata (``column_name``,
    ``test_metadata``) as the primary source for test attributes.

    Tests that *reference* the model via ``depends_on.nodes`` but are owned
    by another model (e.g. ``relationships`` tests) are reported in a
    separate ``referential_tests`` list.

    Args:
        asset_id: Short model name (e.g. ``"fct_sales_pipeline"``).
        manifest_path: Path to dbt manifest.json.

    Returns:
        Dict with ``asset_id``, ``tests``, and ``referential_tests`` keys.
        On error, returns ``error_response(asset_id, message)``.

        Example:
            {"asset_id": "fct_sales_pipeline",
             "tests": [
                 {"name": "not_null_fct_sales_pipeline_opportunity_id",
                  "column": "opportunity_id", "type": "not_null",
                  "severity": "error"},
             ],
             "referential_tests": [
                 {"name": "relationships_...", "column": "opportunity_id",
                  "type": "relationships", "severity": "error",
                  "owner": "fct_revenue_recognition"},
             ]}
    """
    try:
        nodes = _load_manifest(manifest_path)
        unique_id = _resolve_asset_id(asset_id, nodes)
    except ValueError as exc:
        logger.error("Failed to load manifest for tests: %s", exc)
        return error_response(asset_id, str(exc))
    except FileNotFoundError as exc:
        logger.error("Manifest file not found for tests: %s", exc)
        return error_response(asset_id, f"Manifest not found: {exc}")

    tests = []
    referential_tests = []

    for uid, node in nodes.items():
        if not uid.startswith("test."):
            continue

        deps = node.get("depends_on", {}).get("nodes", [])
        if unique_id not in deps:
            continue

        attached = node.get("attached_node")
        if attached is not None and attached != unique_id:
            referential_tests.append(
                _build_test_entry(
                    uid, node, owner=_attached_model_name(attached)
                )
            )
            continue

        tests.append(_build_test_entry(uid, node))

    return {
        "asset_id": asset_id,
        "tests": tests,
        "referential_tests": referential_tests,
    }


def _build_test_entry(
    unique_id: str, node: dict, owner: str | None = None
) -> dict:
    entry = {
        "name": _resolve_test_name(unique_id, node),
        "column": _resolve_test_column(node),
        "type": _resolve_test_type(unique_id, node),
        "severity": _resolve_severity(node),
    }
    if owner is not None:
        entry["owner"] = owner
    return entry


def _attached_model_name(attached_node: str) -> str:
    """Extract the short model name from a full attached_node unique_id."""
    parts = attached_node.split(".")
    if len(parts) >= 3:
        return parts[2]
    return attached_node


def _resolve_test_type(unique_id: str, node: dict) -> str:
    """Resolve test type from manifest metadata, falling back to unique_id parsing."""
    test_meta = node.get("test_metadata", {})
    name = test_meta.get("name")
    if name:
        return name

    return _parse_test_type_from_uid(unique_id)


def _resolve_test_column(node: dict) -> str | None:
    """Resolve column name from manifest metadata."""
    return node.get("column_name") or node.get("tags", {}).get("column_name")


def _resolve_severity(node: dict) -> str:
    """Resolve severity from manifest config, defaulting to 'error'.

    Normalises to lowercase so callers can compare against the
    canonical forms ``"error"`` and ``"warn"`` regardless of how
    dbt stores the value in the manifest.
    """
    config = node.get("config", {})
    severity = config.get("severity")
    if severity:
        return str(severity).lower()

    test_meta = node.get("test_metadata", {})
    kwargs = test_meta.get("kwargs", {})
    severity = kwargs.get("severity")
    if severity:
        return str(severity).lower()

    return "error"


def _resolve_test_name(unique_id: str, node: dict) -> str:
    """Resolve a human-readable test name from the manifest node."""
    name = node.get("name")
    if name:
        return name

    logger.warning(
        "Test node missing 'name' field, falling back to unique_id: %s",
        unique_id,
    )
    parts = unique_id.split(".")
    if len(parts) >= 3:
        name_part = parts[2]
        last_underscore = name_part.rfind("_")
        if last_underscore > 0:
            maybe_hash = name_part[last_underscore + 1:]
            if maybe_hash and all(c in "0123456789abcdef" for c in maybe_hash):
                return name_part[:last_underscore]
    return unique_id


def _parse_test_type_from_uid(unique_id: str) -> str:
    """Fallback: extract test type from unique_id when test_metadata is absent."""
    KNOWN_TYPES = ("not_null", "accepted_values", "unique", "relationships")

    parts = unique_id.split(".")
    if len(parts) >= 3:
        name_part = parts[2]
        for test_type in KNOWN_TYPES:
            prefix = test_type + "_"
            if name_part.startswith(prefix):
                return test_type

    return "unknown"
