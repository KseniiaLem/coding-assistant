"""Dependencies injected into every agent run."""

from collections.abc import Callable
from dataclasses import dataclass, field

from rich.console import Console


@dataclass
class AgentDeps:
    """State a single run needs: console, mode flags, and the event log."""

    console: Console
    plan_mode: bool = False
    # How to ask the human before a file is deleted. None means deletions
    # are not allowed in this session (e.g. web UI with the toggle off).
    confirm_delete: Callable[[str], bool] | None = None
    # Tool-action log entries collected during a run (shown in the web UI).
    events: list[str] = field(default_factory=list)
