import json

import duckdb
import pytest


@pytest.fixture
def sample_manifest_dict():
    return {
        "nodes": {
            "model.tracey_demo.stg_salesforce__opportunity": {
                "name": "stg_salesforce__opportunity",
                "resource_type": "model",
                "meta": {"domain": "staging"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_salesforce__opportunity.sql",
            },
            "model.tracey_demo.stg_finance__revenue": {
                "name": "stg_finance__revenue",
                "resource_type": "model",
                "meta": {"domain": "staging"},
                "depends_on": {"nodes": []},
                "compiled_path": "models/staging/stg_finance__revenue.sql",
            },
            "model.tracey_demo.fct_sales_pipeline": {
                "name": "fct_sales_pipeline",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {"nodes": ["model.tracey_demo.stg_salesforce__opportunity"]},
                "compiled_path": "models/marts/fct_sales_pipeline.sql",
            },
            "model.tracey_demo.fct_revenue_recognition": {
                "name": "fct_revenue_recognition",
                "resource_type": "model",
                "meta": {"domain": "finance"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.stg_finance__revenue",
                        "model.tracey_demo.fct_sales_pipeline",
                    ]
                },
                "compiled_path": "models/marts/fct_revenue_recognition.sql",
            },
            "model.tracey_demo.rpt_commissions": {
                "name": "rpt_commissions",
                "resource_type": "model",
                "meta": {"domain": "sales"},
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.fct_sales_pipeline",
                        "model.tracey_demo.fct_revenue_recognition",
                    ]
                },
                "compiled_path": "models/marts/rpt_commissions.sql",
            },
            "test.tracey_demo.not_null_fct_sales_pipeline_opportunity_id.3404c82367": {
                "name": "not_null_fct_sales_pipeline_opportunity_id",
                "resource_type": "test",
                "column_name": "opportunity_id",
                "attached_node": "model.tracey_demo.fct_sales_pipeline",
                "depends_on": {"nodes": ["model.tracey_demo.fct_sales_pipeline"]},
            },
            "test.tracey_demo.accepted_values_fct_sales_pipeline_stage__prospecting__qualification__proposal__negotiation__closed_won__closed_lost.6542ed473c": {
                "name": "accepted_values_fct_sales_pipeline_stage",
                "resource_type": "test",
                "column_name": "stage",
                "attached_node": "model.tracey_demo.fct_sales_pipeline",
                "depends_on": {"nodes": ["model.tracey_demo.fct_sales_pipeline"]},
            },
            "test.tracey_demo.relationships_fct_revenue_recognition_opportunity_id__opportunity_id__ref_fct_sales_pipeline_.1a0ec672c0": {
                "name": "relationships_fct_revenue_recognition_opportunity_id__opportunity_id__ref_fct_sales_pipeline_",
                "resource_type": "test",
                "column_name": "opportunity_id",
                "attached_node": "model.tracey_demo.fct_revenue_recognition",
                "test_metadata": {
                    "name": "relationships",
                    "kwargs": {
                        "to": "ref('fct_sales_pipeline')",
                        "field": "opportunity_id",
                    },
                },
                "depends_on": {
                    "nodes": [
                        "model.tracey_demo.fct_sales_pipeline",
                        "model.tracey_demo.fct_revenue_recognition",
                    ]
                },
            },
            "test.tracey_demo.unique_dim_customer_customer_id.b42affccd1": {
                "name": "unique_dim_customer_customer_id",
                "resource_type": "test",
                "column_name": "customer_id",
                "attached_node": "model.tracey_demo.dim_customer",
                "depends_on": {"nodes": ["model.tracey_demo.dim_customer"]},
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
    models_dir = tmp_path / "models" / "marts"
    models_dir.mkdir(parents=True)

    (models_dir / "fct_sales_pipeline.sql").write_text(
        "SELECT opportunity_id, lead_score, amount FROM raw_salesforce_opportunity\n"
    )

    (models_dir / "fct_revenue_recognition.sql").write_text(
        "SELECT r.opportunity_id, sp.lead_score * 0.3 AS lead_score_weighted "
        "FROM stg_finance__revenue r "
        "JOIN fct_sales_pipeline sp ON r.opportunity_id = sp.opportunity_id\n"
    )

    (models_dir / "rpt_commissions.sql").write_text(
        "SELECT sp.opportunity_id, "
        "CASE WHEN rr.lead_score_weighted > 10 THEN sp.amount * 0.10 "
        "ELSE sp.amount * 0.05 END AS commission "
        "FROM fct_sales_pipeline sp "
        "LEFT JOIN fct_revenue_recognition rr "
        "ON sp.opportunity_id = rr.opportunity_id "
        "WHERE rr.lead_score_weighted IS NOT NULL\n"
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
            ('fct_sales_pipeline', '2026-05-15 10:00:00',
             'column_drop', 'sales_engineer', 'Removed legacy lead_score'),
            ('fct_sales_pipeline', '2026-06-20 14:30:00',
             'refactor', 'sales_engineer', 'Optimized pipeline joins'),
            ('fct_revenue_recognition', '2026-04-01 09:00:00',
             'column_add', 'fpanda_lead', 'Added lead_score_weighted column')
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
            ('fct_sales_pipeline', 'sales', 450, 3),
            ('fct_sales_pipeline', 'finance', 320, 2),
            ('fct_revenue_recognition', 'finance', 280, 2),
            ('fct_revenue_recognition', 'sales', 45, 0)
    """)

    con.close()
    return str(db)
