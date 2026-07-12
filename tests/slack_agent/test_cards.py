from tracey.slack_agent.cards import (
    build_checklist_blocks,
    build_close_pr_modal,
    build_cross_team_summary_blocks,
    build_impact_card,
    build_marked_outdated_confirmation,
    build_pr_closed_confirmation_blocks,
    build_pr_confirmation_blocks,
    build_pr_modal,
    build_stale_thread_block,
)


class TestBuildImpactCard:
    def itShould_produce_valid_blocks_list(self, sample_analysis):
        blocks = build_impact_card(sample_analysis)
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def itShould_not_exceed_50_blocks(self, sample_analysis):
        blocks = build_impact_card(sample_analysis)
        assert len(blocks) < 50

    def itShould_include_action_buttons(self, sample_analysis):
        blocks = build_impact_card(sample_analysis)
        action_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(action_blocks) >= 1
        elements = action_blocks[0].get("elements", [])
        assert len(elements) == 5

    def itShould_include_header_block(self, sample_analysis):
        blocks = build_impact_card(sample_analysis)
        headers = [b for b in blocks if b.get("type") == "header"]
        assert len(headers) >= 1


class TestBuildChecklistBlocks:
    def itShould_produce_valid_blocks(self, sample_analysis):
        migration = sample_analysis["migration_order"]["migration_order"]
        tests = sample_analysis["tests"]["tests"]
        ref_tests = sample_analysis["tests"]["referential_tests"]

        blocks = build_checklist_blocks(migration, tests, ref_tests, "fct_sales_pipeline")
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"

    def itShould_handle_empty_migration_order(self, sample_analysis):
        blocks = build_checklist_blocks([], [], [], "fct_sales_pipeline")
        assert any("No downstream models" in str(b) for b in blocks)


class TestBuildStaleThreadBlock:
    def itShould_produce_section_and_context_blocks(self):
        blocks = build_stale_thread_block(
            "thread_ts_1",
            "C456",
            "https://slack.example.com/thread/1",
            "2026-06-20T14:30:00",
            "https://slack.example.com/thread/current",
        )
        assert len(blocks) == 2
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "context"


class TestBuildPrModal:
    def itShould_return_valid_modal_view(self):
        view = build_pr_modal("fct_sales_pipeline")
        assert view["type"] == "modal"
        assert view["callback_id"] == "annotate_pr_modal"
        assert "blocks" in view
        assert "submit" in view
        assert "close" in view

    def itShould_include_pr_number_input(self):
        view = build_pr_modal("fct_sales_pipeline")
        input_blocks = [b for b in view["blocks"] if b["type"] == "input"]
        assert len(input_blocks) == 4

    def itShould_have_private_metadata(self):
        view = build_pr_modal("fct_sales_pipeline")
        assert "private_metadata" in view


class TestBuildPrConfirmationBlocks:
    def itShould_include_pr_link_when_url_provided(self):
        blocks = build_pr_confirmation_blocks("42", "https://github.com/o/r/pull/42", "fct_sales_pipeline")
        assert any("https://github.com" in str(b) for b in blocks)

    def itShould_handle_missing_pr_url(self):
        blocks = build_pr_confirmation_blocks("42", None, "fct_sales_pipeline")
        assert isinstance(blocks, list)
        assert len(blocks) >= 1


class TestBuildClosePrModal:
    def itShould_return_valid_modal_view(self):
        view = build_close_pr_modal("fct_sales_pipeline")
        assert view["type"] == "modal"
        assert view["callback_id"] == "close_pr_modal"
        assert "blocks" in view
        assert view["submit"]["text"] == "Close PR"

    def itShould_prefill_pr_number(self):
        view = build_close_pr_modal("fct_sales_pipeline", pr_number="7")
        pr_block = next(b for b in view["blocks"] if b.get("block_id") == "pr_number_block")
        assert pr_block["element"]["initial_value"] == "7"

    def itShould_include_optional_comment_input(self):
        view = build_close_pr_modal("fct_sales_pipeline")
        comment_block = next(b for b in view["blocks"] if b.get("block_id") == "close_comment_block")
        assert comment_block["optional"] is True

    def itShould_have_private_metadata(self):
        view = build_close_pr_modal("fct_sales_pipeline")
        assert "private_metadata" in view


class TestBuildPrClosedConfirmationBlocks:
    def itShould_include_pr_link_when_url_provided(self):
        blocks = build_pr_closed_confirmation_blocks("42", "https://github.com/o/r/pull/42", "fct_sales_pipeline")
        assert any("https://github.com" in str(b) for b in blocks)

    def itShould_handle_missing_pr_url(self):
        blocks = build_pr_closed_confirmation_blocks("42", None, "fct_sales_pipeline")
        assert isinstance(blocks, list)
        assert len(blocks) >= 1


class TestBuildCrossTeamSummary:
    def itShould_include_expert_mentions(self):
        blocks = build_cross_team_summary_blocks(
            "fct_sales_pipeline",
            "review-fct_sales_pipeline",
            ["U001", "U002"],
            "C789",
        )
        assert any("<@U001>" in str(b) for b in blocks)

    def itShould_handle_no_experts(self):
        blocks = build_cross_team_summary_blocks(
            "fct_sales_pipeline",
            "review-fct_sales_pipeline",
            [],
            None,
        )
        assert isinstance(blocks, list)
        assert len(blocks) > 0


class TestBuildMarkedOutdatedConfirmation:
    def itShould_include_count(self):
        blocks = build_marked_outdated_confirmation(3)
        assert "3" in str(blocks)
