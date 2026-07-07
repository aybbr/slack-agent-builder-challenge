from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = str(DATA_DIR / "demo.duckdb")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(DB_PATH) as con:
        con.execute("""
            CREATE OR REPLACE TABLE usage_stats (
                asset_id TEXT,
                domain TEXT,
                query_count INTEGER,
                dashboard_count INTEGER
            )
        """)

        con.execute("""
            INSERT INTO usage_stats VALUES
                ('fct_sales_pipeline',       'sales',   450, 3),
                ('fct_sales_pipeline',       'finance', 320, 2),
                ('fct_revenue_recognition',  'finance', 280, 2),
                ('fct_revenue_recognition',  'sales',    45, 0),
                ('rpt_commissions',          'sales',   190, 1),
                ('rpt_commissions',          'finance',  85, 1),
                ('dim_customer',             'sales',   600, 4),
                ('dim_customer',             'finance', 120, 1)
        """)

    print(f"Seeded usage_stats into {DB_PATH}")


if __name__ == "__main__":
    main()
