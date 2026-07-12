import logging

from github import Github, GithubException

logger = logging.getLogger(__name__)


def _parse_pr_number(pr_id: str) -> int:
    """Parse a PR id string into an integer.

    Args:
        pr_id: Pull request number as a string (e.g. ``'42'``).

    Returns:
        The PR number as an ``int``.

    Raises:
        ValueError: If ``pr_id`` is not a valid integer.
    """
    return int(pr_id)


def _format_github_error(exc: GithubException, repo_name: str) -> str:
    """Translate a PyGithub exception into a user-facing message.

    Adds a helpful hint when the failure is a 403 caused by insufficient
    repository access on the personal access token.

    Args:
        exc: The exception raised by PyGithub.
        repo_name: Repository in ``owner/repo`` format (used in the hint).

    Returns:
        A safe, human-readable error message.
    """
    msg = str(exc)
    if "403" in msg and "Resource not accessible" in msg:
        hint = (
            " Token is valid but lacks repository access. "
            "Verify your PAT has 'Contents: Read and write' on "
            f"{repo_name}."
        )
        return f"{exc}{hint}"
    return str(exc)


def annotate_pr(
    pr_id: str,
    summary: str,
    repo_name: str,
    token: str,
    labels: list[str] | None = None,
) -> dict:
    """Post a comment on a GitHub pull request and apply labels.

    Uses PyGithub to authenticate with a personal access token and
    create an issue comment on the specified PR.

    Args:
        pr_id: Pull request number as string (e.g. ``'42'``).
        summary: Markdown-formatted comment body.
        repo_name: Repository in ``owner/repo`` format.
        token: GitHub personal access token.
        labels: Optional list of label names to apply.  Labels that don't
            exist will be created automatically by GitHub.

    Returns:
        ``{"success": True, "pr_url": "https://github.com/owner/repo/pull/42"}``
        OR ``{"error": "Failed to annotate PR: <message>"}``
    """
    try:
        pr_number = _parse_pr_number(pr_id)
    except (ValueError, TypeError):
        return {"error": f"Invalid PR ID: {pr_id}"}

    try:
        gh = Github(token)
        repo = gh.get_repo(repo_name)
        pull = repo.get_pull(pr_number)
        pull.create_issue_comment(summary)

        for label in labels or []:
            try:
                pull.add_to_labels(label)
            except GithubException:
                logger.debug("Could not add label '%s' to PR %s", label, pr_id)
    except GithubException as exc:
        logger.error("GitHub API error for PR %s: %s", pr_id, exc)
        return {"error": f"Failed to annotate PR: {_format_github_error(exc, repo_name)}"}

    return {"success": True, "pr_url": pull.html_url}


def close_pr(
    pr_id: str,
    repo_name: str,
    token: str,
    comment: str | None = None,
) -> dict:
    """Close a GitHub pull request, optionally leaving a comment first.

    Uses PyGithub to authenticate with a personal access token, post an
    optional closing comment, then set the pull request state to
    ``closed``.  The branch and commits are preserved — only the PR is
    closed, so it can be reopened if needed.

    Args:
        pr_id: Pull request number as string (e.g. ``'42'``).
        repo_name: Repository in ``owner/repo`` format.
        token: GitHub personal access token.
        comment: Optional Markdown-formatted comment posted before closing
            (e.g. the reason for closing and next steps).

    Returns:
        ``{"success": True, "pr_url": "...", "state": "closed"}``
        OR ``{"error": "Failed to close PR: <message>"}``
    """
    try:
        pr_number = _parse_pr_number(pr_id)
    except (ValueError, TypeError):
        return {"error": f"Invalid PR ID: {pr_id}"}

    try:
        gh = Github(token)
        repo = gh.get_repo(repo_name)
        pull = repo.get_pull(pr_number)

        if comment:
            pull.create_issue_comment(comment)

        pull.edit(state="closed")
    except GithubException as exc:
        logger.error("GitHub API error closing PR %s: %s", pr_id, exc)
        return {"error": f"Failed to close PR: {_format_github_error(exc, repo_name)}"}

    return {"success": True, "pr_url": pull.html_url, "state": "closed"}
