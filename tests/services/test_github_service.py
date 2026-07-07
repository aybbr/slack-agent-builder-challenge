from unittest.mock import MagicMock, patch

from tracey.services.github_service import annotate_pr


class TestAnnotatePr:
    @patch("tracey.services.github_service.Github")
    def itShould_post_comment_on_success(self, mock_github):
        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/42"
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_gh_instance = MagicMock()
        mock_gh_instance.get_repo.return_value = mock_repo
        mock_github.return_value = mock_gh_instance

        result = annotate_pr("42", "Test summary", "owner/repo", "fake-token")

        assert result["success"] is True
        assert result["pr_url"] == "https://github.com/owner/repo/pull/42"
        mock_pr.create_issue_comment.assert_called_once_with("Test summary")

    @patch("tracey.services.github_service.Github")
    def itShould_return_error_on_api_failure(self, mock_github):
        from github import GithubException

        mock_gh_instance = MagicMock()
        mock_gh_instance.get_repo.side_effect = GithubException(404, "Not Found", {})
        mock_github.return_value = mock_gh_instance

        result = annotate_pr("42", "Test summary", "owner/repo", "fake-token")

        assert "error" in result

    def itShould_return_error_for_invalid_pr_id(self):
        result = annotate_pr("not-a-number", "summary", "owner/repo", "token")
        assert "error" in result
        assert "Invalid PR ID" in result["error"]
