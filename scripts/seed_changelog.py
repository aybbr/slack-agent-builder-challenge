import duckdb
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = str(DATA_DIR / "demo.duckdb")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(DB_PATH)

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
            ('fct_revenue_recognition', '2026-04-01 09:00:00',
             'column_add', 'fpanda_lead',
             'Added lead_score_weighted column for pipeline integration'),
            ('fct_sales_pipeline', '2026-05-15 10:00:00',
             'column_drop', 'sales_engineer',
             'Removed legacy lead_score calculation logic'),
            ('fct_sales_pipeline', '2026-06-20 14:30:00',
             'refactor', 'sales_engineer',
             'Optimized pipeline joins for query performance')
    """)

    con.close()
    print(f"Seeded schema_changelog into {DB_PATH}")


if __name__ == "__main__":
    main()
