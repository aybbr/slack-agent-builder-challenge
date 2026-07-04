import json
import logging

import sqlglot
import sqlglot.errors
import sqlglot.expressions as exp
from pathlib import Path

from tracey.services._manifest_helpers import (
    _get_downstream_models,
    _get_node,
    _get_upstream_models,
    _load_manifest,
    _resolve_asset_id,
    _topological_sort,
)
from tracey.utils.errors import error_response

logger = logging.getLogger(__name__)


def get_lineage(asset_id: str, manifest_path: str) -> dict:
    """Return upstream and downstream lineage for a dbt model.

    Resolves short model name to full unique_id, then extracts direct
    upstream models and all transitive downstream models with cross-domain
    detection based on manifest meta.domain tags.

    Args:
        asset_id: Short model name (e.g. 'fct_sales_pipeline').
        manifest_path: Path to dbt manifest.json.

    Returns:
        Dict with asset_id, domain, upstream, and downstream lists.
        On error, returns error_response(asset_id, message).
    """
    try:
        nodes = _load_manifest(manifest_path)
        unique_id = _resolve_asset_id(asset_id, nodes)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Failed to load manifest for lineage: %s", exc)
        return error_response(asset_id, str(exc))

    node = _get_node(unique_id, nodes)
    if node is None:
        return error_response(asset_id, f"Node '{unique_id}' not found in manifest")

    asset_domain = node.get("meta", {}).get("domain", "unknown")

    upstream = []
    for uid in _get_upstream_models(unique_id, nodes):
        parent = _get_node(uid, nodes)
        upstream.append({
            "id": parent.get("name", uid) if parent else uid,
            "domain": parent.get("meta", {}).get("domain", "unknown") if parent else "unknown",
        })

    downstream = []
    for uid in _get_downstream_models(unique_id, nodes):
        child = _get_node(uid, nodes)
        if child is None:
            continue
        child_domain = child.get("meta", {}).get("domain", "unknown")
        downstream.append({
            "id": child.get("name", uid),
            "domain": child_domain,
            "cross_domain": child_domain != asset_domain,
        })

    return {
        "asset_id": asset_id,
        "domain": asset_domain,
        "upstream": upstream,
        "downstream": downstream,
    }


def get_migration_order(asset_id: str, manifest_path: str) -> dict:
    """Return topologically sorted migration order for an asset and all its
    transitive downstream models.

    Args:
        asset_id: Short model name.
        manifest_path: Path to dbt manifest.json.

    Returns:
        Dict with ordered migration plan including domain and cross-domain tags.
        On error, returns error_response(asset_id, message).
    """
    try:
        nodes = _load_manifest(manifest_path)
        unique_id = _resolve_asset_id(asset_id, nodes)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Failed to load manifest for migration order: %s", exc)
        return error_response(asset_id, str(exc))

    node = _get_node(unique_id, nodes)
    if node is None:
        return error_response(asset_id, f"Node '{unique_id}' not found in manifest")

    asset_domain = node.get("meta", {}).get("domain", "unknown")

    downstream_ids = _get_downstream_models(unique_id, nodes)
    all_ids = [unique_id] + downstream_ids

    try:
        sorted_ids = _topological_sort(all_ids, nodes)
    except ValueError as exc:
        return error_response(asset_id, str(exc))

    order = []
    order_num = 0
    for uid in sorted_ids:
        n = _get_node(uid, nodes)
        if n is None:
            continue
        order_num += 1
        dom = n.get("meta", {}).get("domain", "unknown")
        order.append({
            "id": n.get("name", uid),
            "domain": dom,
            "order": order_num,
            "is_source": uid == unique_id,
            "cross_domain": dom != asset_domain,
        })

    return {
        "asset_id": asset_id,
        "domain": asset_domain,
        "migration_order": order,
    }


def get_column_lineage(
    asset_id: str,
    column_name: str,
    manifest_path: str,
    compiled_dir: str,
) -> dict:
    """Trace a column through downstream dbt models using SQLGlot.

    Parses compiled SQL files for all transitive downstream models and
    detects references to the given column via AST walking.

    Each usage entry includes a ``confidence`` field:
    ``"high"`` when the column reference is qualified with a table alias
    that matches the upstream model; ``"low"`` when the column name appears
    without a qualifying table reference.

    Args:
        asset_id: Short model name containing the column.
        column_name: Column name to trace.
        manifest_path: Path to dbt manifest.json.
        compiled_dir: Directory containing compiled SQL files.

    Returns:
        Dict with asset_id, column_name, downstream_usages list, and
        warnings list. On error, returns error_response(asset_id, message).
    """
    try:
        nodes = _load_manifest(manifest_path)
        unique_id = _resolve_asset_id(asset_id, nodes)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Failed to load manifest for column lineage: %s", exc)
        return error_response(asset_id, str(exc), column_name=column_name)

    downstream_ids = _get_downstream_models(unique_id, nodes)
    compiled_base = Path(compiled_dir)

    usages: list[dict] = []
    warnings: list[str] = []

    for uid in downstream_ids:
        child = _get_node(uid, nodes)
        if child is None:
            continue
        child_name = child.get("name", uid)
        compiled_rel = child.get("compiled_path")
        if not compiled_rel:
            warnings.append(f"No compiled_path for {child_name}")
            continue
        compiled_path = compiled_base / compiled_rel
        if not compiled_path.exists():
            msg = f"Compiled SQL not found for {child_name}: {compiled_path}"
            logger.warning(msg)
            warnings.append(msg)
            continue

        sql_text = compiled_path.read_text()
        child_usages = _find_column_usages(
            sql_text, asset_id, column_name, child_name, warnings
        )
        usages.extend(child_usages)

    return {
        "asset_id": asset_id,
        "column_name": column_name,
        "downstream_usages": usages,
        "warnings": warnings,
    }


def _find_column_usages(
    sql_text: str,
    upstream_model: str,
    column_name: str,
    downstream_model: str,
    warnings_out: list[str],
) -> list[dict]:
    """Parse SQL with SQLGlot and find column references from the upstream model."""

    try:
        parsed = sqlglot.parse(sql_text, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        msg = f"Failed to parse SQL for {downstream_model}: {exc}"
        logger.warning(msg)
        warnings_out.append(msg)
        return []

    alias_map = _build_alias_map(parsed, upstream_model)
    results: list[dict] = []

    for statement in parsed:
        for node in statement.walk():
            if not isinstance(node, exp.Column):
                continue

            col_name = _get_column_name(node)
            if not col_name or col_name.lower() != column_name.lower():
                continue

            table_ref = _get_table_ref(node)
            if table_ref and table_ref.lower() not in alias_map:
                continue

            usage_type = _detect_usage_type(node)
            output_column = _find_output_column(node)

            results.append({
                "model": downstream_model,
                "column": output_column if output_column else col_name,
                "usage_type": usage_type,
                "confidence": "high" if table_ref else "low",
            })

    return results


def _get_column_name(node: exp.Column) -> str | None:
    """Extract the column name from a SQLGlot Column node."""
    this = node.this
    if isinstance(this, exp.Identifier):
        return this.name
    if hasattr(this, "name"):
        return str(this.name)
    return str(this) if this else None


def _get_table_ref(node: exp.Column) -> str | None:
    """Extract the table/alias reference from a SQLGlot Column node."""
    table = node.args.get("table")
    if table is None:
        return None
    if isinstance(table, exp.Identifier):
        return table.name
    if hasattr(table, "name"):
        return str(table.name)
    return str(table)


def _build_alias_map(
    parsed_statements: list, upstream_model: str
) -> set[str]:
    """Build a set of known aliases/references for the upstream model.

    Walks the AST for ``Table`` nodes whose bare name matches
    ``upstream_model``.  For schema-qualified identifiers (e.g.
    ``"demo"."main_main"."fct_sales_pipeline"``), SQLGlot returns the
    last segment as ``node.name``, so matching still works.
    """
    aliases: set[str] = {upstream_model.lower()}
    aliases.add(f'"{upstream_model.lower()}"')

    for statement in parsed_statements:
        for node in statement.walk():
            if isinstance(node, exp.Table):
                name = node.name
                if name:
                    name_lower = str(name).strip('"').lower()
                    if name_lower == upstream_model.lower():
                        alias = node.alias
                        if alias:
                            aliases.add(alias.lower())
                            aliases.add(f'"{alias.lower()}"')

    return aliases


def _detect_usage_type(column_node: exp.Column) -> str:
    """Determine how a column is used by walking up the AST."""
    current = column_node

    while current:
        parent = current.parent

        if parent is None:
            break

        if isinstance(parent, exp.Where):
            return "where_clause"

        if isinstance(parent, exp.Join):
            return "join_condition"

        if isinstance(parent, exp.Select):
            return "select"

        if isinstance(
            parent,
            (exp.Binary, exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Case, exp.When, exp.If),
        ):
            return "expression"

        current = parent

    return "select"


def _find_output_column(column_node: exp.Column) -> str | None:
    """Find the output column name by walking up to the nearest Alias node."""
    current = column_node.parent
    while current:
        if isinstance(current, exp.Alias):
            alias = current.alias
            return str(alias).strip('"') if alias else None
        if isinstance(current, exp.Select):
            break
        current = current.parent
    return None
