"""File tools (read/write/search/delete) sandboxed to one folder."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

from coding_assistant.deps import AgentDeps

_SANDBOX = Path("sandbox")

# tool name -> (log verb, argument holding the target) for the action log.
_LOG_LABELS = {
    "search_files": ("searching", "pattern"),
    "read_file": ("reading", "path"),
    "write_file": ("writing", "path"),
    "delete_file": ("deleting", "path"),
}


def _path_sandbox(path: str) -> Path:
    """Resolve a path inside the sandbox, refusing escapes.

    Security fix: without the check below, a path like "../.env" would
    resolve outside the sandbox and expose files such as the API key.

    Parameters
    ----------
    path : str
        The relative path to resolve.

    Returns
    -------
    Path
        The absolute path inside the sandbox.

    Raises
    ------
    ValueError
        If the resolved path escapes the sandbox.

    """
    root = _SANDBOX.resolve()
    target = (root / path).resolve()

    if not target.is_relative_to(root):
        raise ValueError(f"Path escapes the sandbox: {path}")

    return target


def read_file(path: str) -> str:
    """Read the contents of the file.

    Parameters
    ----------
    path : str
        The relative path to the file.

    Returns
    -------
    str
        The contents of the file, or an error message starting with
        "Error:" if the file cannot be read.

    """
    try:
        return _path_sandbox(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except ValueError as exc:
        return f"Error: {exc}"


def write_file(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
    """Write contents to a file, creating parent directories if needed.

    Parameters
    ----------
    ctx : RunContext[AgentDeps]
        The run context (injected, not model-controlled).
    path : str
        The relative path to the file.
    content : str
        The contents to be written to the file.

    Returns
    -------
    str
        A confirmation message, or an error message starting with "Error:".

    """
    if ctx.deps.plan_mode:
        return (
            "Error: planning mode is active. Present the design and wait "
            "for user approval instead of writing files."
        )

    try:
        file_path = _path_sandbox(path)
    except ValueError as exc:
        return f"Error: {exc}"

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    return f"Written: {path}"


def search_files(pattern: str) -> list[str] | str:
    """Search for files matching a glob pattern.

    Parameters
    ----------
    pattern : str
        The glob pattern to match files (e.g., "**/*.py", "test_*.py").

    Returns
    -------
    list[str] | str
        A list of relative file paths matching the pattern, or an error
        message starting with "Error:" if the pattern is invalid.

    """
    _SANDBOX.mkdir(exist_ok=True)
    root = _SANDBOX.resolve()
    try:
        matches = list(_SANDBOX.glob(pattern))
    except (ValueError, NotImplementedError) as exc:
        return f"Error: invalid pattern {pattern!r}: {exc}"

    # Security: ".." in a pattern would match files outside the sandbox
    # (e.g. "../*" reaches .env), so keep only paths inside it.
    return [
        str(p.resolve().relative_to(root))
        for p in matches
        if p.resolve() != root and p.resolve().is_relative_to(root)
    ]


def delete_file(ctx: RunContext[AgentDeps], path: str) -> str:
    """Delete a file. The user must confirm the deletion first.

    Parameters
    ----------
    ctx : RunContext[AgentDeps]
        The run context (injected, not model-controlled).
    path : str
        The relative path to the file.

    Returns
    -------
    str
        A confirmation message, an error message starting with "Error:",
        or a note that the user declined the deletion.

    """
    if ctx.deps.plan_mode:
        return (
            "Error: planning mode is active. No files can be deleted."
        )

    try:
        target = _path_sandbox(path)
    except ValueError as exc:
        return f"Error: {exc}"

    # Human-in-the-loop: how to confirm depends on the interface (terminal
    # y/N prompt for the CLI, the "allow delete" toggle for the web UI).
    if ctx.deps.confirm_delete is None:
        return (
            "Error: deletions are disabled in this session. Ask the user "
            "to enable them (web UI: the 'allow delete' toggle) and retry."
        )
    if not ctx.deps.confirm_delete(path):
        return "Deletion declined by the user."

    try:
        target.unlink()
    except FileNotFoundError:
        return f"Error: file not found: {path}"

    return f"Deleted: {path}"


@dataclass
class FileOperations(AbstractCapability[AgentDeps]):
    """File tools plus the hook that logs every file action live."""

    def get_toolset(self) -> FunctionToolset:
        """Expose the four file tools to the agent."""
        toolset = FunctionToolset()

        toolset.add_function(read_file)
        toolset.add_function(write_file)
        toolset.add_function(search_files)
        toolset.add_function(delete_file)

        return toolset

    async def before_tool_execute(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Log the file action before it runs (terminal + web event log)."""
        if call.tool_name in _LOG_LABELS:
            verb, key = _LOG_LABELS[call.tool_name]
            entry = f"{verb}: {args.get(key)}"
            ctx.deps.console.log(entry)
            ctx.deps.events.append(entry)

        return args
