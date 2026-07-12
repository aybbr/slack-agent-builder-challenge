"""Centralised environment variable configuration.

Single source of truth for all env vars used across agent tools,
MCP server tools, and Slack handlers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnvConfig:
    """Immutable snapshot of runtime environment configuration."""

    manifest_path: str
    duckdb_path: str
    github_token: str
    github_repo: str
    dbt_project_dir: str

    @classmethod
    def from_env(cls) -> EnvConfig:
        """Build config from the current process environment."""
        return cls(
            manifest_path=os.environ.get("MANIFEST_PATH", "dbt_project/target/manifest.json"),
            duckdb_path=os.environ.get("DUCKDB_PATH", "data/demo.duckdb"),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            github_repo=os.environ.get("GITHUB_REPO", ""),
            dbt_project_dir=os.environ.get("DBT_PROJECT_DIR", "dbt_project"),
        )
