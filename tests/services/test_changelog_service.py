from tracey.services.changelog_service import get_last_change


class TestGetLastChange:
    def itShould_return_nested_last_change_when_found(self, db_path):
        result = get_last_change("fct_sales_pipeline", db_path)
        assert result["asset_id"] == "fct_sales_pipeline"
        change = result["last_change"]
        assert change is not None
        assert change["change_type"] == "refactor"
        assert "2026-06-20" in change["changed_at"]

    def itShould_return_null_last_change_for_unchanged_asset(self, db_path):
        result = get_last_change("dim_customer", db_path)
        assert result["asset_id"] == "dim_customer"
        assert result["last_change"] is None

    def itShould_return_error_for_missing_db(self):
        result = get_last_change("fct_sales_pipeline", "/nonexistent/db.duckdb")
        assert "error" in result

    def itShould_include_all_change_fields(self, db_path):
        result = get_last_change("fct_revenue_recognition", db_path)
        change = result["last_change"]
        assert change is not None
        assert "changed_at" in change
        assert "change_type" in change
        assert "changed_by" in change
        assert "summary" in change
        assert "T" in change["changed_at"]
