"""Thread-safe context variable for injecting TraceyDeps into tools.

Same pattern as Casey's ``casey_deps_var`` from the Slack sample agent.
"""

from contextvars import ContextVar

from tracey.agent.deps import TraceyDeps

tracey_deps_var: ContextVar[TraceyDeps | None] = ContextVar("tracey_deps", default=None)
