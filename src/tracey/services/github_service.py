import logging

logger = logging.getLogger(__name__)


def annotate_pr(
    pr_id: str, summary: str, repo_name: str, token: str
) -> dict:
    """Post a comment on a GitHub pull request.

    Uses PyGithub to authenticate with a personal access token and
    create an issue comment on the specified PR.

    Args:
        pr_id: Pull request number as string (e.g. '42').
        summary: Markdown-formatted comment body.
        repo_name: Repository in 'owner/repo' format.
        token: GitHub personal access token.

    Returns:
        {"success": True, "pr_url": "https://github.com/owner/repo/pull/42"}
        OR
        {"error": "Failed to annotate PR: <message>"}
    """
    try:
        from github import Github, GithubException
    except ImportError:
        return {"error": "PyGithub is not installed"}

    try:
        pr_number = int(pr_id)
    except (ValueError, TypeError):
        return {"error": f"Invalid PR ID: {pr_id}"}

    try:
        gh = Github(token)
        repo = gh.get_repo(repo_name)
        pull = repo.get_pull(pr_number)
        pull.create_issue_comment(summary)
        return {"success": True, "pr_url": pull.html_url}
    except GithubException as exc:
        logger.error("GitHub API error for PR %s: %s", pr_id, exc)
        return {"error": f"Failed to annotate PR: {exc}"}
    except Exception as exc:
        logger.error("Unexpected error annotating PR %s: %s", pr_id, exc)
        return {"error": f"Failed to annotate PR: {exc}"}
