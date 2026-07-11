from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = str(DATA_DIR / "demo.duckdb")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(DB_PATH) as con:
        con.execute("""
            CREATE OR REPLACE TABLE schema_changelog (
                asset_id TEXT,
                changed_at TIMESTAMP,
                change_type TEXT,
                changed_by TEXT,
                summary TEXT
            )
        """)

        con.execute("""
            INSERT INTO schema_changelog VALUES
                ('fct_sales_pipeline', '2026-04-15 10:00:00',
                 'column_drop', 'alex.chen',
                 'Removed legacy lead_score column from fct_sales_pipeline'),
                ('fct_sales_pipeline', '2026-05-20 14:30:00',
                 'refactor', 'alex.chen',
                 'Introduced lead_score_tier bucketing via int_pipeline_enrichment'),
                ('fct_sales_pipeline', '2026-06-20 09:00:00',
                 'column_add', 'alex.chen',
                 'Added weighted_pipeline_value based on lead_score_tier'),
                ('fct_revenue', '2026-06-22 11:00:00',
                 'refactor', 'maya.patel',
                 'Adjusted revenue calculation to use lead_score_tier from pipeline enrichment'),
                ('int_account_360', '2026-05-20 14:30:00',
                 'refactor', 'sam.rodriguez',
                 'Refactored account 360 to join account_score and product_usage — diamond convergence'),
                ('int_account_360', '2026-06-25 16:00:00',
                 'column_add', 'sam.rodriguez',
                 'Added account_segment and lead_score_tier to unified view'),
                ('dim_account', '2026-06-25 16:30:00',
                 'column_add', 'sam.rodriguez',
                 'Surfaced lead_score_tier to dimension for dashboard consumption'),
                ('rpt_exec_dashboard', '2026-06-28 08:00:00',
                 'refactor', 'maya.patel',
                 'Added executive_summary_flag driven by lead_score_tier and forecast_category'),
                ('stg_sf_accounts', '2026-03-01 09:00:00',
                 'schema_change', 'sam.rodriguez',
                 'Added is_partner flag — propagates to account_segment in int_account_360')
        """)

    print(f"Seeded schema_changelog into {DB_PATH}")


if __name__ == "__main__":
    main()
