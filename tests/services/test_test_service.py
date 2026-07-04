from tracey.services.test_service import get_tests


class TestGetTests:
    def itShould_find_tests_owned_by_asset(self, manifest_path):
        result = get_tests("fct_sales_pipeline", manifest_path)
        assert len(result["tests"]) == 2
        test_names = {t["name"] for t in result["tests"]}
        assert "not_null_fct_sales_pipeline_opportunity_id" in test_names
        assert "accepted_values_fct_sales_pipeline_stage" in test_names

    def itShould_report_referential_tests_separately(self, manifest_path):
        result = get_tests("fct_sales_pipeline", manifest_path)
        assert len(result["referential_tests"]) == 1
        ref = result["referential_tests"][0]
        assert ref["type"] == "relationships"
        assert ref["owner"] == "fct_revenue_recognition"

    def itShould_extract_test_type_from_metadata(self, manifest_path):
        result = get_tests("fct_sales_pipeline", manifest_path)
        types = {t["type"] for t in result["tests"]}
        assert "not_null" in types or "accepted_values" in types

    def itShould_extract_column_name(self, manifest_path):
        result = get_tests("fct_sales_pipeline", manifest_path)
        columns = {t["column"] for t in result["tests"]}
        assert "opportunity_id" in columns

    def itShould_assign_error_severity_by_default(self, manifest_path):
        result = get_tests("fct_sales_pipeline", manifest_path)
        for test in result["tests"]:
            if test["type"] == "not_null":
                assert test["severity"] == "error"

    def itShould_return_empty_for_untested_asset(self, manifest_path):
        result = get_tests("stg_salesforce__opportunity", manifest_path)
        assert result["tests"] == []
        assert result["referential_tests"] == []

    def itShould_return_error_for_nonexistent_asset(self, manifest_path):
        result = get_tests("nonexistent_model", manifest_path)
        assert "error" in result
        assert result["asset_id"] == "nonexistent_model"

    def itShould_include_asset_id_in_response(self, manifest_path):
        result = get_tests("fct_sales_pipeline", manifest_path)
        assert result["asset_id"] == "fct_sales_pipeline"
