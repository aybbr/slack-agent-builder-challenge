"""Tests for prefilter.py — deterministic model-name detection gate."""

import pytest

import tracey.slack_agent.prefilter as prefilter_module


@pytest.fixture(autouse=True)
def _clear_prefilter_cache():
    """Ensure clean cache state before every test."""
    prefilter_module._get_model_names.cache_clear()


class TestHasModelMention:
    def itShould_return_model_name_when_text_contains_known_model(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("We need to drop lead_score from fct_sales_pipeline")
        assert result == "fct_sales_pipeline"

    def itShould_match_case_insensitively(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("FCT_SALES_PIPELINE needs a refactor")
        assert result == "fct_sales_pipeline"

    def itShould_return_None_when_no_model_mentioned(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("The weather is nice today")
        assert result is None

    def itShould_not_match_partial_model_names(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("modifying_fct_sales_pipeline_v2 is the new model")
        assert result is None

    def itShould_return_None_for_empty_text(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("")
        assert result is None

    def itShould_match_longest_model_name_first(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("What about stg_salesforce__opportunity and fct_sales_pipeline?")
        assert result == "stg_salesforce__opportunity"

    def itShould_handle_model_names_with_underscores(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("check stg_salesforce__opportunity for duplicates")
        assert result == "stg_salesforce__opportunity"

    def itShould_handle_text_with_special_characters(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        result = prefilter_module.has_model_mention("DROP COLUMN lead_score FROM fct_sales_pipeline;")
        assert result == "fct_sales_pipeline"


class TestGetModelNames:
    def itShould_return_frozenset_of_model_names(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        names = prefilter_module._get_model_names()
        assert isinstance(names, frozenset)
        assert "fct_sales_pipeline" in names
        assert "fct_revenue_recognition" in names
        assert "rpt_commissions" in names

    def itShould_not_include_test_node_names(self, monkeypatch, manifest_path):
        monkeypatch.setattr(prefilter_module, "_MANIFEST_PATH", manifest_path)

        names = prefilter_module._get_model_names()
        for name in names:
            assert not name.startswith("not_null")
            assert not name.startswith("accepted_values")
            assert not name.startswith("unique_")
            assert not name.startswith("relationships")
