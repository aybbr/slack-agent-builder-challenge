from tracey.slack_agent.triggers import detect_trigger


class TestDetectTrigger:
    def itShould_detect_model_and_intent(self):
        result = detect_trigger(
            "We need to drop fct_sales_pipeline next week"
        )
        assert result is not None
        assert result["model"] == "fct_sales_pipeline"
        assert result["intent"] == "drop"

    def itShouldnt_detect_trigger_without_intent_keyword(self):
        result = detect_trigger(
            "The fct_sales_pipeline looks great today"
        )
        assert result is None

    def itShouldnt_detect_trigger_without_model_name(self):
        result = detect_trigger("We should drop that table")
        assert result is None

    def itShould_detect_rename_intent(self):
        result = detect_trigger(
            "Please rename fct_revenue_recognition"
        )
        assert result is not None
        assert result["model"] == "fct_revenue_recognition"
        assert result["intent"] == "rename"

    def itShould_detect_refactor_intent(self):
        result = detect_trigger(
            "Let's refactor rpt_commissions"
        )
        assert result is not None
        assert result["model"] == "rpt_commissions"
        assert result["intent"] == "refactor"

    def itShould_extract_column_when_mentioned(self):
        result = detect_trigger(
            "We're dropping the lead_score column from fct_sales_pipeline"
        )
        assert result is not None
        assert result["model"] == "fct_sales_pipeline"
        assert result["intent"] == "dropping"
        assert result["column"] == "lead_score"

    def itShould_extract_column_with_remove_intent(self):
        result = detect_trigger(
            "remove lead_score from fct_sales_pipeline"
        )
        assert result is not None
        assert result["column"] == "lead_score"

    def itShould_be_case_insensitive(self):
        result = detect_trigger(
            "DROP FCT_SALES_PIPELINE NOW"
        )
        assert result is not None
        assert result["model"] == "fct_sales_pipeline"
        assert result["intent"] == "drop"

    def itShould_detect_modify_intent(self):
        result = detect_trigger(
            "We should modify dim_customer schema"
        )
        assert result is not None
        assert result["model"] == "dim_customer"
        assert result["intent"] == "modify"

    def itShouldnt_confuse_intent_keyword_as_column(self):
        result = detect_trigger(
            "drop the column from fct_sales_pipeline"
        )
        assert result is not None
        assert result["model"] == "fct_sales_pipeline"
        assert result["column"] is None

    def itShould_not_match_partial_model_name(self):
        result = detect_trigger("Let's drop sales_pipeline")
        assert result is None

    def itShould_match_longest_model_first(self):
        result = detect_trigger(
            "deprecate stg_salesforce__opportunity"
        )
        assert result is not None
        assert result["model"] == "stg_salesforce__opportunity"
