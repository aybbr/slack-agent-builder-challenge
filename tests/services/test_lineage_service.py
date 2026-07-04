from tracey.services.lineage_service import (
    get_column_lineage,
    get_lineage,
    get_migration_order,
)


class TestGetLineage:
    def itShould_return_upstream_models(self, manifest_path):
        result = get_lineage("fct_sales_pipeline", manifest_path)
        assert "error" not in result
        upstream_ids = [u["id"] for u in result["upstream"]]
        assert "stg_salesforce__opportunity" in upstream_ids

    def itShould_detect_cross_domain_downstream(self, manifest_path):
        result = get_lineage("fct_sales_pipeline", manifest_path)
        downstream = {d["id"]: d for d in result["downstream"]}
        assert downstream["fct_revenue_recognition"]["cross_domain"] is True
        assert downstream["fct_revenue_recognition"]["domain"] == "finance"

    def itShould_not_flag_same_domain_as_cross(self, manifest_path):
        result = get_lineage("fct_sales_pipeline", manifest_path)
        downstream = {d["id"]: d for d in result["downstream"]}
        assert downstream["rpt_commissions"]["cross_domain"] is False

    def itShould_return_error_for_unknown_asset(self, manifest_path):
        result = get_lineage("nonexistent_model", manifest_path)
        assert "error" in result

    def itShould_return_domain_of_asset(self, manifest_path):
        result = get_lineage("fct_sales_pipeline", manifest_path)
        assert result["domain"] == "sales"

    def itShould_return_empty_downstream_for_leaf(self, manifest_path):
        result = get_lineage("rpt_commissions", manifest_path)
        assert result["downstream"] == []


class TestGetMigrationOrder:
    def itShould_order_source_before_dependents(self, manifest_path):
        result = get_migration_order("fct_sales_pipeline", manifest_path)
        order_ids = [m["id"] for m in result["migration_order"]]
        fct_idx = order_ids.index("fct_sales_pipeline")
        rec_idx = order_ids.index("fct_revenue_recognition")
        rpt_idx = order_ids.index("rpt_commissions")
        assert fct_idx < rec_idx < rpt_idx

    def itShould_mark_first_item_as_source(self, manifest_path):
        result = get_migration_order("fct_sales_pipeline", manifest_path)
        assert result["migration_order"][0]["is_source"] is True
        assert result["migration_order"][0]["id"] == "fct_sales_pipeline"

    def itShould_flag_cross_domain_in_migration(self, manifest_path):
        result = get_migration_order("fct_sales_pipeline", manifest_path)
        by_id = {m["id"]: m for m in result["migration_order"]}
        assert by_id["fct_revenue_recognition"]["cross_domain"] is True
        assert by_id["rpt_commissions"]["cross_domain"] is False

    def itShould_have_contiguous_order_numbers(self, manifest_path):
        result = get_migration_order("fct_sales_pipeline", manifest_path)
        orders = [m["order"] for m in result["migration_order"]]
        assert orders == list(range(1, len(orders) + 1))


class TestGetColumnLineage:
    def itShould_detect_expression_usage(self, manifest_path, compiled_dir):
        result = get_column_lineage(
            "fct_sales_pipeline", "lead_score", manifest_path, compiled_dir
        )
        usages = result.get("downstream_usages", [])
        revenue_usages = [
            u for u in usages if u["model"] == "fct_revenue_recognition"
        ]
        assert any(u["usage_type"] == "expression" for u in revenue_usages)

    def itShould_detect_column_in_downstream(self, manifest_path, compiled_dir):
        result = get_column_lineage(
            "fct_sales_pipeline", "lead_score", manifest_path, compiled_dir
        )
        usages = result.get("downstream_usages", [])
        model_names = {u["model"] for u in usages}
        assert "fct_revenue_recognition" in model_names

    def itShould_return_empty_for_unreferenced_column(self, manifest_path, compiled_dir):
        result = get_column_lineage(
            "fct_sales_pipeline", "nonexistent_column", manifest_path, compiled_dir
        )
        assert result.get("downstream_usages", []) == []

    def itShould_return_error_for_missing_manifest(self, compiled_dir):
        result = get_column_lineage(
            "no_such_model", "lead_score", "/nonexistent/path.json", compiled_dir
        )
        assert "error" in result

    def itShould_detect_output_column_name(self, manifest_path, compiled_dir):
        result = get_column_lineage(
            "fct_sales_pipeline", "lead_score", manifest_path, compiled_dir
        )
        usages = result.get("downstream_usages", [])
        output_columns = [u.get("column") for u in usages]
        assert any(c == "lead_score_weighted" for c in output_columns)

    def itShould_include_warnings_field(self, manifest_path, compiled_dir):
        result = get_column_lineage(
            "fct_sales_pipeline", "lead_score", manifest_path, compiled_dir
        )
        assert "warnings" in result
