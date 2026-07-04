import logging
from datetime import datetime

import duckdb

logger = logging.getLogger(__name__)


def get_last_change(asset_id: str, db_path: str) -> dict:
    """Return the most recent schema change for an asset.

    Queries the schema_changelog table in DuckDB for the latest record
    matching the given asset_id.

    Args:
        asset_id: Short model name (e.g. 'fct_sales_pipeline').
        db_path: Path to the DuckDB database file.

    Returns:
        Dict with asset_id and last_change (nested dict or None).

        Example with change:
            {"asset_id": "fct_sales_pipeline",
             "last_change": {
                 "changed_at": "2026-06-20T14:30:00",
                 "change_type": "refactor",
                 "changed_by": "sales_engineer",
                 "summary": "Optimized pipeline joins"}}

        Example without change:
            {"asset_id": "fct_sales_pipeline", "last_change": None}
    """
    try:
        with duckdb.connect(db_path) as con:
            result = con.execute(
                """
                SELECT asset_id, changed_at, change_type, changed_by, summary
                FROM schema_changelog
                WHERE asset_id = ?
                ORDER BY changed_at DESC
                LIMIT 1
                """,
                [asset_id],
            ).fetchone()
    except duckdb.Error as exc:
        logger.error(
            "DuckDB error querying schema_changelog for %s: %s", asset_id, exc
        )
        return {"asset_id": asset_id, "error": f"Database error: {exc}"}

    if result is None or len(result) == 0:
        return {"asset_id": asset_id, "last_change": None}

    changed_at = result[1]
    if isinstance(changed_at, datetime):
        changed_at = changed_at.isoformat()

    return {
        "asset_id": result[0],
        "last_change": {
            "changed_at": changed_at,
            "change_type": result[2],
            "changed_by": result[3],
            "summary": result[4],
        },
    }
