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
                ('stg_sf_opportunities',      'sales',   320, 1),
                ('stg_sf_accounts',           'sales',   410, 2),
                ('stg_sf_accounts',           'product', 180, 1),
                ('stg_sf_accounts',           'finance',  45, 0),
                ('stg_product_events',        'product', 520, 3),
                ('stg_billing_invoices',      'finance', 280, 2),
                ('stg_billing_subscriptions', 'finance', 250, 1),
                ('int_account_score',         'sales',   380, 2),
                ('int_product_usage',         'product', 450, 3),
                ('int_product_usage',         'sales',    85, 1),
                ('int_revenue_monthly',       'finance', 310, 3),
                ('int_account_360',           'sales',   290, 2),
                ('int_account_360',           'product', 140, 1),
                ('int_account_360',           'finance', 120, 1),
                ('int_pipeline_enrichment',   'sales',   350, 2),
                ('int_pipeline_enrichment',   'finance',  90, 1),
                ('int_forecast_input',        'finance', 200, 2),
                ('int_forecast_input',        'sales',    40, 0),
                ('fct_sales_pipeline',        'sales',   450, 4),
                ('fct_sales_pipeline',        'finance', 320, 3),
                ('fct_sales_pipeline',        'product', 125, 1),
                ('fct_revenue',               'finance', 380, 3),
                ('fct_revenue',               'sales',   160, 2),
                ('dim_account',               'sales',   520, 4),
                ('dim_account',               'product', 210, 2),
                ('dim_account',               'finance', 180, 2),
                ('fct_product_engagement',    'product', 480, 3),
                ('fct_product_engagement',    'sales',    70, 1),
                ('rpt_commissions',           'sales',   220, 2),
                ('rpt_commissions',           'finance',  95, 1),
                ('rpt_exec_dashboard',        'sales',   180, 2),
                ('rpt_exec_dashboard',        'finance', 150, 2),
                ('rpt_exec_dashboard',        'product',  85, 1)
        """)

    print(f"Seeded usage_stats into {DB_PATH}")


if __name__ == "__main__":
    main()
