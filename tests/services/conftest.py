import json

import duckdb
import pytest


@pytest.fixture
def sample_manifest_dict():
    return {
        "nodes": {
            # ---- Staging ----
            "model.tracey_demo.stg_sf_opportunities": {
                "name": "stg_sf_opportunities",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_sf_opportunities.sql",
            },
            "model.tracey_demo.stg_sf_accounts": {
                "name": "stg_sf_accounts",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_sf_accounts.sql",
            },
            "model.tracey_demo.stg_product_events": {
                "name": "stg_product_events",
                "resource_type": "model",
                "meta": {"domain": "product"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_product_events.sql",
            },
            "model.tracey_demo.stg_billing_invoices": {
                "name": "stg_billing_invoices",
                "resource_type": "model",
                "meta": {"domain": "finance"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_billing_invoices.sql",
            },
            "model.tracey_demo.stg_billing_subscriptions": {
                "name": "stg_billing_subscriptions",
                "resource_type": "model",
                "meta": {"domain": "finance"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_billing_subscriptions.sql",
            },
            # ---- Intermediate ----
            "model.tracey_demo.int_account_score": {
                "name": "int_account_score",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.stg_sf_opportunities",
                        "model.tracey_demo.stg_sf_accounts",
                    ]
                },
                "compiled_path": "models/intermediate/int_account_score.sql",
            },
            "model.tracey_demo.int_product_usage": {
                "name": "int_product_usage",
                "resource_type": "model",
                "meta": {"domain": "product"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.stg_product_events",
                        "model.tracey_demo.stg_sf_accounts",
                    ]
                },
                "compiled_path": "models/intermediate/int_product_usage.sql",
            },
            "model.tracey_demo.int_revenue_monthly": {
                "name": "int_revenue_monthly",
                "resource_type": "model",
                "meta": {"domain": "finance"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.stg_billing_invoices",
                        "model.tracey_demo.stg_billing_subscriptions",
                    ]
                },
                "compiled_path": "models/intermediate/int_revenue_monthly.sql",
            },
            "model.tracey_demo.int_account_360": {
                "name": "int_account_360",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.int_account_score",
                        "model.tracey_demo.int_product_usage",
                    ]
                },
                "compiled_path": "models/intermediate/int_account_360.sql",
            },
            "model.tracey_demo.int_pipeline_enrichment": {
                "name": "int_pipeline_enrichment",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.stg_sf_opportunities",
                        "model.tracey_demo.int_account_360",
                    ]
                },
                "compiled_path": "models/intermediate/int_pipeline_enrichment.sql",
            },
            "model.tracey_demo.int_forecast_input": {
                "name": "int_forecast_input",
                "resource_type": "model",
                "meta": {"domain": "finance"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.int_revenue_monthly",
                        "model.tracey_demo.int_pipeline_enrichment",
                    ]
                },
                "compiled_path": "models/intermediate/int_forecast_input.sql",
            },
            # ---- Marts ----
            "model.tracey_demo.fct_sales_pipeline": {
                "name": "fct_sales_pipeline",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {"nodes": ["model.tracey_demo.int_pipeline_enrichment"]},
                "compiled_path": "models/marts/fct_sales_pipeline.sql",
            },
            "model.tracey_demo.fct_revenue": {
                "name": "fct_revenue",
                "resource_type": "model",
                "meta": {"domain": "finance"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.int_revenue_monthly",
                        "model.tracey_demo.int_pipeline_enrichment",
                        "model.tracey_demo.int_forecast_input",
                    ]
                },
                "compiled_path": "models/marts/fct_revenue.sql",
            },
            "model.tracey_demo.dim_account": {
                "name": "dim_account",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {"nodes": ["model.tracey_demo.int_account_360"]},
                "compiled_path": "models/marts/dim_account.sql",
            },
            "model.tracey_demo.fct_product_engagement": {
                "name": "fct_product_engagement",
                "resource_type": "model",
                "meta": {"domain": "product"},
                "depends_on": {"nodes": ["model.tracey_demo.int_product_usage"]},
                "compiled_path": "models/marts/fct_product_engagement.sql",
            },
            # ---- Reports ----
            "model.tracey_demo.rpt_commissions": {
                "name": "rpt_commissions",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.fct_sales_pipeline",
                        "model.tracey_demo.fct_revenue",
                    ]
                },
                "compiled_path": "models/marts/rpt_commissions.sql",
            },
            "model.tracey_demo.rpt_exec_dashboard": {
                "name": "rpt_exec_dashboard",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.dim_account",
                        "model.tracey_demo.fct_revenue",
                        "model.tracey_demo.fct_product_engagement",
                    ]
                },
                "compiled_path": "models/marts/rpt_exec_dashboard.sql",
            },
            # ---- Tests ----
            "test.tracey_demo.not_null_fct_sales_pipeline_opportunity_id.3404c82367": {
                "name": "not_null_fct_sales_pipeline_opportunity_id",
                "resource_type": "test",
                "column_name": "opportunity_id",
                "attached_node": "model.tracey_demo.fct_sales_pipeline",
                "depends_on": {"nodes": ["model.tracey_demo.fct_sales_pipeline"]},
            },
            "test.tracey_demo.unique_stg_sf_opportunities_opportunity_id.ab12cd34": {
                "name": "unique_stg_sf_opportunities_opportunity_id",
                "resource_type": "test",
                "column_name": "opportunity_id",
                "attached_node": "model.tracey_demo.stg_sf_opportunities",
                "depends_on": {"nodes": ["model.tracey_demo.stg_sf_opportunities"]},
            },
            "test.tracey_demo.accepted_values_stg_sf_opportunities_stage.6542ed47": {
                "name": "accepted_values_stg_sf_opportunities_stage",
                "resource_type": "test",
                "column_name": "stage",
                "attached_node": "model.tracey_demo.stg_sf_opportunities",
                "depends_on": {"nodes": ["model.tracey_demo.stg_sf_opportunities"]},
            },
            "test.tracey_demo.relationships_fct_revenue_account_id__account_id__ref_fct_sales_pipeline_.1a0ec67": {
                "name": "relationships_fct_revenue_account_id",
                "resource_type": "test",
                "column_name": "account_id",
                "attached_node": "model.tracey_demo.fct_revenue",
                "test_metadata": {
                    "name": "relationships",
                    "kwargs": {
                        "to": "ref('fct_sales_pipeline')",
                        "field": "account_id",
                    },
                },
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.fct_sales_pipeline",
                        "model.tracey_demo.fct_revenue",
                    ]
                },
            },
        }
    }


@pytest.fixture
def manifest_path(sample_manifest_dict, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(sample_manifest_dict))
    return str(path)


@pytest.fixture
def compiled_dir(tmp_path):
    staging_dir = tmp_path / "models" / "staging"
    intermediate_dir = tmp_path / "models" / "intermediate"
    marts_dir = tmp_path / "models" / "marts"
    for d in (staging_dir, intermediate_dir, marts_dir):
        d.mkdir(parents=True, exist_ok=True)

    (staging_dir / "stg_sf_opportunities.sql").write_text(
        "SELECT opportunity_id, account_id, lead_score, amount, stage FROM raw_salesforce_opportunities\n"
    )

    (intermediate_dir / "int_account_score.sql").write_text(
        "SELECT a.account_id, AVG(o.lead_score) AS avg_lead_score "
        "FROM stg_sf_accounts a "
        "LEFT JOIN stg_sf_opportunities o ON a.account_id = o.account_id "
        "GROUP BY a.account_id\n"
    )

    (intermediate_dir / "int_product_usage.sql").write_text(
        "SELECT pe.account_id, a.account_name, "
        "SUM(pe.user_count) AS total_users "
        "FROM stg_product_events pe "
        "LEFT JOIN stg_sf_accounts a ON pe.account_id = a.account_id "
        "GROUP BY pe.account_id, a.account_name\n"
    )

    (intermediate_dir / "int_account_360.sql").write_text(
        "SELECT acs.account_id, acs.avg_lead_score, "
        "pu.total_users, "
        "CASE WHEN acs.avg_lead_score >= 80 THEN 'high' "
        "WHEN acs.avg_lead_score >= 50 THEN 'medium' "
        "ELSE 'low' END AS lead_score_tier "
        "FROM int_account_score acs "
        "LEFT JOIN int_product_usage pu ON acs.account_id = pu.account_id\n"
    )

    (intermediate_dir / "int_pipeline_enrichment.sql").write_text(
        "SELECT o.opportunity_id, o.account_id, "
        "a360.lead_score_tier, a360.account_segment, "
        "o.lead_score AS raw_lead_score, "
        "CASE WHEN a360.lead_score_tier = 'high' THEN o.amount * 1.2 "
        "ELSE o.amount END AS weighted_pipeline_value "
        "FROM stg_sf_opportunities o "
        "LEFT JOIN int_account_360 a360 ON o.account_id = a360.account_id\n"
    )

    (intermediate_dir / "int_forecast_input.sql").write_text(
        "SELECT rm.account_id, rm.revenue_month, "
        "pe.lead_score_tier, pe.weighted_pipeline_value, "
        "rm.total_revenue + COALESCE(pe.weighted_pipeline_value * 0.3, 0) AS forecast_revenue "
        "FROM int_revenue_monthly rm "
        "LEFT JOIN int_pipeline_enrichment pe ON rm.account_id = pe.account_id\n"
    )

    (marts_dir / "fct_sales_pipeline.sql").write_text(
        "SELECT opportunity_id, account_id, lead_score_tier, raw_lead_score, "
        "weighted_pipeline_value FROM int_pipeline_enrichment\n"
    )

    (marts_dir / "fct_revenue.sql").write_text(
        "SELECT rm.account_id, pe.lead_score_tier, "
        "CASE WHEN pe.lead_score_tier = 'high' THEN rm.total_revenue * 1.15 "
        "ELSE rm.total_revenue END AS adjusted_revenue "
        "FROM int_revenue_monthly rm "
        "LEFT JOIN int_pipeline_enrichment pe ON rm.account_id = pe.account_id\n"
    )

    (marts_dir / "rpt_commissions.sql").write_text(
        "SELECT sp.account_id, sp.amount, sp.lead_score_tier, "
        "CASE WHEN sp.lead_score_tier = 'high' THEN sp.amount * 0.12 "
        "WHEN sp.lead_score_tier = 'medium' THEN sp.amount * 0.08 "
        "ELSE sp.amount * 0.05 END AS commission "
        "FROM fct_sales_pipeline sp "
        "LEFT JOIN fct_revenue r ON sp.account_id = r.account_id\n"
    )

    return str(tmp_path)


@pytest.fixture
def db_path(tmp_path):
    db = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db))

    con.execute("""
        CREATE TABLE schema_changelog (
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
             'column_drop', 'alex.chen', 'Removed legacy lead_score'),
            ('fct_sales_pipeline', '2026-05-20 14:30:00',
             'refactor', 'alex.chen', 'Introduced lead_score_tier bucketing'),
            ('fct_sales_pipeline', '2026-06-20 09:00:00',
             'column_add', 'alex.chen', 'Added weighted_pipeline_value'),
            ('fct_revenue', '2026-06-22 11:00:00',
             'refactor', 'maya.patel', 'Adjusted revenue calculation'),
            ('int_account_360', '2026-06-25 16:00:00',
             'column_add', 'sam.rodriguez', 'Added lead_score_tier to 360 view')
    """)

    con.execute("""
        CREATE TABLE usage_stats (
            asset_id TEXT,
            domain TEXT,
            query_count INTEGER,
            dashboard_count INTEGER
        )
    """)
    con.execute("""
        INSERT INTO usage_stats VALUES
            ('fct_sales_pipeline', 'sales', 450, 4),
            ('fct_sales_pipeline', 'finance', 320, 3),
            ('fct_revenue', 'finance', 380, 3),
            ('fct_revenue', 'sales', 160, 2),
            ('rpt_commissions', 'sales', 220, 2),
            ('rpt_commissions', 'finance', 95, 1),
            ('dim_account', 'sales', 520, 4),
            ('dim_account', 'finance', 180, 2)
    """)

    con.close()
    return str(db)
