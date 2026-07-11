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
        assert "int_pipeline_enrichment" in upstream_ids

    def itShould_detect_cross_domain_downstream(self, manifest_path):
        result = get_lineage("int_pipeline_enrichment", manifest_path)
        downstream = {d["id"]: d for d in result["downstream"]}
        assert downstream["fct_revenue"]["cross_domain"] is True
        assert downstream["fct_revenue"]["domain"] == "finance"

    def itShould_not_flag_same_domain_as_cross(self, manifest_path):
        result = get_lineage("int_pipeline_enrichment", manifest_path)
        downstream = {d["id"]: d for d in result["downstream"]}
        assert downstream["fct_sales_pipeline"]["cross_domain"] is False

    def itShould_return_error_for_unknown_asset(self, manifest_path):
        result = get_lineage("nonexistent_model", manifest_path)
        assert "error" in result

    def itShould_return_domain_of_asset(self, manifest_path):
        result = get_lineage("fct_sales_pipeline", manifest_path)
        assert result["domain"] == "sales"

    def itShould_return_empty_downstream_for_leaf(self, manifest_path):
        result = get_lineage("rpt_exec_dashboard", manifest_path)
        assert result["downstream"] == []


class TestGetMigrationOrder:
    def itShould_order_source_before_dependents(self, manifest_path):
        result = get_migration_order("int_pipeline_enrichment", manifest_path)
        order_ids = [m["id"] for m in result["migration_order"]]
        pipe_idx = order_ids.index("int_pipeline_enrichment")
        sales_idx = order_ids.index("fct_sales_pipeline")
        revenue_idx = order_ids.index("fct_revenue")
        comm_idx = order_ids.index("rpt_commissions")
        assert pipe_idx < sales_idx < comm_idx
        assert pipe_idx < revenue_idx

    def itShould_mark_first_item_as_source(self, manifest_path):
        result = get_migration_order("int_pipeline_enrichment", manifest_path)
        sources = [m for m in result["migration_order"] if m["is_source"]]
        assert len(sources) == 1
        assert sources[0]["id"] == "int_pipeline_enrichment"

    def itShould_flag_cross_domain_in_migration(self, manifest_path):
        result = get_migration_order("int_pipeline_enrichment", manifest_path)
        by_id = {m["id"]: m for m in result["migration_order"]}
        assert by_id["fct_revenue"]["cross_domain"] is True
        assert by_id["fct_sales_pipeline"]["cross_domain"] is False

    def itShould_have_contiguous_order_numbers(self, manifest_path):
        result = get_migration_order("int_pipeline_enrichment", manifest_path)
        orders = [m["order"] for m in result["migration_order"]]
        assert orders == list(range(1, len(orders) + 1))


class TestGetColumnLineage:
    def itShould_detect_expression_usage(self, manifest_path, compiled_dir):
        result = get_column_lineage("fct_sales_pipeline", "lead_score_tier", manifest_path, compiled_dir)
        usages = result.get("downstream_usages", [])
        comm_usages = [u for u in usages if u["model"] == "rpt_commissions"]
        assert any(u["usage_type"] == "expression" for u in comm_usages)

    def itShould_detect_column_in_downstream(self, manifest_path, compiled_dir):
        result = get_column_lineage("fct_sales_pipeline", "lead_score_tier", manifest_path, compiled_dir)
        usages = result.get("downstream_usages", [])
        model_names = {u["model"] for u in usages}
        assert "rpt_commissions" in model_names

    def itShould_return_empty_for_unreferenced_column(self, manifest_path, compiled_dir):
        result = get_column_lineage("fct_sales_pipeline", "nonexistent_column", manifest_path, compiled_dir)
        assert result.get("downstream_usages", []) == []

    def itShould_return_error_for_missing_manifest(self, compiled_dir):
        result = get_column_lineage("no_such_model", "lead_score_tier", "/nonexistent/path.json", compiled_dir)
        assert "error" in result

    def itShould_detect_output_column_name(self, manifest_path, compiled_dir):
        result = get_column_lineage("fct_sales_pipeline", "lead_score_tier", manifest_path, compiled_dir)
        usages = result.get("downstream_usages", [])
        output_columns = [u.get("column") for u in usages]
        assert any(c == "commission" for c in output_columns)

    def itShould_include_warnings_field(self, manifest_path, compiled_dir):
        result = get_column_lineage("fct_sales_pipeline", "lead_score_tier", manifest_path, compiled_dir)
        assert "warnings" in result


class TestAliasDetection:
    """Verify _build_alias_map handles schema-qualified table refs."""

    def itShould_match_schema_qualified_table_with_alias(self, manifest_path, compiled_dir, tmp_path):
        models_dir = tmp_path / "models" / "marts"
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "rpt_commissions.sql").write_text(
            "SELECT sp.lead_score_tier, sp.amount, sp.lead_score_tier, "
            "CASE WHEN sp.lead_score_tier = 'high' THEN sp.amount * 0.12 "
            "ELSE sp.amount * 0.08 END AS commission "
            'FROM "demo"."main_main"."fct_sales_pipeline" sp '
            'LEFT JOIN "demo"."main_main"."fct_revenue" r '
            "ON sp.account_id = r.account_id\n"
        )
        result = get_column_lineage("fct_sales_pipeline", "lead_score_tier", manifest_path, str(tmp_path))
        usages = result.get("downstream_usages", [])
        rpt_usages = [u for u in usages if u["model"] == "rpt_commissions"]
        qualified = [u for u in rpt_usages if u["confidence"] == "high" and u["usage_type"] == "select"]
        assert len(qualified) >= 1, (
            f"Expected high-confidence select usage for lead_score_tier in rpt_commissions "
            f"with schema-qualified FROM clause, got {rpt_usages}"
        )

    def itShould_flag_unqualified_column_as_low_confidence(self, manifest_path, compiled_dir, tmp_path):
        models_dir = tmp_path / "models" / "marts"
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "rpt_commissions.sql").write_text(
            "SELECT lead_score_tier, sp.amount, lead_score_tier * 0.05 AS commission FROM fct_sales_pipeline sp\n"
        )
        result = get_column_lineage("fct_sales_pipeline", "lead_score_tier", manifest_path, str(tmp_path))
        usages = result.get("downstream_usages", [])
        rpt_usages = [u for u in usages if u["model"] == "rpt_commissions"]
        unqualified = [u for u in rpt_usages if u["column"] == "lead_score_tier" and u["confidence"] == "low"]
        assert len(unqualified) >= 1, f"Expected low-confidence match for unqualified lead_score_tier, got {rpt_usages}"
