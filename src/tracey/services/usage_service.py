import logging

import duckdb

from tracey.utils.errors import error_response

logger = logging.getLogger(__name__)


def get_usage(asset_id: str, db_path: str) -> dict:
    """Return aggregated usage statistics for an asset grouped by domain.

    Queries the usage_stats table in DuckDB and computes per-domain
    query and dashboard counts plus overall totals.

    Args:
        asset_id: Short model name (e.g. 'fct_sales_pipeline').
        db_path: Path to the DuckDB database file.

    Returns:
        Dict with by_domain list and total counts.

        Example:
            {"asset_id": "fct_sales_pipeline",
             "by_domain": [{"domain": "sales", "queries": 450, "dashboards": 3}, ...],
             "total_queries": 770, "total_dashboards": 5}
    """
    try:
        with duckdb.connect(db_path) as con:
            rows = con.execute(
                """
                SELECT domain,
                       SUM(query_count) AS queries,
                       SUM(dashboard_count) AS dashboards
                FROM usage_stats
                WHERE asset_id = ?
                GROUP BY domain
                ORDER BY queries DESC
                """,
                [asset_id],
            ).fetchall()
    except duckdb.Error as exc:
        logger.error(
            "DuckDB error querying usage_stats for %s: %s", asset_id, exc
        )
        return error_response(asset_id, f"Database error: {exc}")

    by_domain = [
        {"domain": row[0], "queries": row[1], "dashboards": row[2]}
        for row in rows
    ]

    total_queries = sum(d["queries"] for d in by_domain)
    total_dashboards = sum(d["dashboards"] for d in by_domain)

    return {
        "asset_id": asset_id,
        "by_domain": by_domain,
        "total_queries": total_queries,
        "total_dashboards": total_dashboards,
    }
