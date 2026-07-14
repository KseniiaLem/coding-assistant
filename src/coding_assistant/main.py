"""Terminal interface: the conversation loop and agent configuration."""

import asyncio
import signal
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from rich.console import Console
from rich.markdown import Markdown

from coding_assistant.capabilities.file_operations import FileOperations
from coding_assistant.capabilities.reasoning_effort import ReasoningEffort
from coding_assistant.capabilities.skills import Skills
from coding_assistant.deps import AgentDeps
from coding_assistant.utils import get_env

_INSTRUCTIONS = (
    "You are a Python coding agent.\n"
    "* Write clear, correct, and minimal Python code.\n"
    "* Follow the user's instructions exactly, do not add extra features.\n"
    "* Prefer the standard library over external dependencies.\n"
    "* Explore the project structure before planning or implementing.\n"
    "* If requirements are unclear, ask a concise clarification question.\n"
    "* Provide a brief summary of your implementation.\n"
    "* Use the available tools.\n"
    "* Comment your code meaningfully: every non-obvious line gets a short\n"
    "  comment explaining WHY it exists, not just what it does.\n"
    "* After creating or changing a file, give the user a short\n"
    "  walkthrough of the code in plain language.\n"
)

_PLAN_MODE_NOTE = (
    "(Planning mode is ON: explore the project and present a design. "
    "Do not create, modify, or delete any files. Wait for approval.)\n"
)

_HELP = (
    "Commands:\n"
    "  /plan  - toggle planning mode (design only, file writes blocked)\n"
    "  /new   - start a new conversation (forget history)\n"
    "  /help  - show this help\n"
    "  exit   - quit\n"
    "Tips: add @low or @high to a request to control reasoning effort.\n"
    "      press Ctrl+C while a request is running to cancel just that "
    "request (the session stays open)."
)


def build_agent() -> Agent[AgentDeps]:
    """Create the configured agent. Shared by the CLI and the web UI."""
    provider = OpenAIProvider(
        base_url=get_env("OPENAI_API_BASE"),
        api_key=get_env("OPENAI_API_KEY"),
    )

    model = OpenAIResponsesModel(
        model_name=get_env("MODEL"),
        provider=provider,
    )

    return Agent[AgentDeps](
        model=model,
        instructions=_INSTRUCTIONS,
        capabilities=[
            FileOperations(),
            ReasoningEffort(),
            Skills(),
        ],
        deps_type=AgentDeps,
    )


async def run_agent() -> None:
    """Run the interactive terminal conversation loop."""
    console = Console()
    Path("sandbox").mkdir(exist_ok=True)

    def confirm_delete(path: str) -> bool:
        answer = console.input(f"Delete {path}? [y/N] ")
        return answer.strip().lower() == "y"

    agent = build_agent()
    deps = AgentDeps(console=console, confirm_delete=confirm_delete)

    message_history: list[ModelMessage] | None = None

    console.print("Coding assistant ready. Type /help for commands.")

    while True:
        user_prompt = console.input(">> ").strip()

        if not user_prompt:
            continue
        if user_prompt.lower() in ("exit", "quit"):
            break
        if user_prompt == "/new":
            message_history = None
            console.print("Started a new conversation.")
            continue
        if user_prompt == "/help":
            console.print(_HELP)
            continue
        if user_prompt == "/plan":
            deps.plan_mode = not deps.plan_mode
            state = "ON" if deps.plan_mode else "OFF"
            console.print(f"Planning mode: {state}")
            continue

        if deps.plan_mode:
            user_prompt = _PLAN_MODE_NOTE + user_prompt

        # Run as a task so Ctrl+C can cancel just this request. A SIGINT
        # handler that cancels the task is reliable; catching
        # KeyboardInterrupt inside a coroutine is not (the signal can land
        # in the event loop machinery and tear the whole loop down first).
        task = asyncio.ensure_future(
            agent.run(user_prompt, message_history=message_history, deps=deps)
        )
        previous = signal.signal(signal.SIGINT, lambda *_: task.cancel())
        try:
            result = await task
        except asyncio.CancelledError:
            console.print("\n[yellow]Request cancelled.[/yellow]")
            continue
        except Exception as exc:  # noqa: BLE001 - keep the session alive
            console.print(f"[red]Request failed:[/red] {exc}")
            console.print("Your conversation is preserved. Try again.")
            continue
        finally:
            # Outside a request, Ctrl+C means "quit" again.
            signal.signal(signal.SIGINT, previous)

        console.print(Markdown(result.output))
        console.print(result.usage())

        message_history = result.all_messages()


def main() -> None:
    """Entry point: run the loop, exit quietly on Ctrl+C / Ctrl+D."""
    try:
        asyncio.run(run_agent())
    except (EOFError, KeyboardInterrupt):
        pass
