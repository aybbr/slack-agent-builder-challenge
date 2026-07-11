from tracey.services.usage_service import get_usage


class TestGetUsage:
    def itShould_aggregate_by_domain(self, db_path):
        result = get_usage("fct_sales_pipeline", db_path)
        domains = [d["domain"] for d in result["by_domain"]]
        assert "sales" in domains
        assert "finance" in domains

    def itShould_compute_correct_totals(self, db_path):
        result = get_usage("fct_sales_pipeline", db_path)
        assert result["total_queries"] == 770
        assert result["total_dashboards"] == 7

    def itShould_return_zero_totals_for_missing_asset(self, db_path):
        result = get_usage("nonexistent_model", db_path)
        assert result["by_domain"] == []
        assert result["total_queries"] == 0
        assert result["total_dashboards"] == 0

    def itShould_return_error_for_missing_db(self):
        result = get_usage("fct_sales_pipeline", "/nonexistent/db.duckdb")
        assert "error" in result

    def itShould_include_asset_id_in_response(self, db_path):
        result = get_usage("fct_sales_pipeline", db_path)
        assert result["asset_id"] == "fct_sales_pipeline"
