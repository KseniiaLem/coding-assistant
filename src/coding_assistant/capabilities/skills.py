"""Dynamic skills: Markdown files the agent can discover and load."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import FunctionToolset

_SKILLS_DIR = Path("skills")


def load_skill(skill_name: str) -> str:
    """Load a skill.

    Parameters
    ----------
    skill_name : str
        The name of the skill to load, as listed in the instructions.

    Returns
    -------
    str
        The contents of the skill file, or an error message starting
        with "Error:".

    """
    # Security: reject names that try to escape the skills directory.
    if "/" in skill_name or "\\" in skill_name or ".." in skill_name:
        return f"Error: invalid skill name: {skill_name}"

    file_path = _SKILLS_DIR / f"{skill_name}.md"
    if not file_path.exists():
        return f"Error: skill not found: {skill_name}"

    skill = frontmatter.load(str(file_path))
    return skill.content


@dataclass
class Skills(AbstractCapability[Any]):
    """Lists available skills in the instructions and loads them on demand."""

    def get_instructions(self) -> str:
        """List every skill (name + description) for the system prompt."""
        result = (
            "You can extend your capabilities by using skills.\n"
            "Use a skill when doing tasks described in the skill.\n\n"
            "You have the following skills available:"
        )

        files = _SKILLS_DIR.glob("*.md")

        for f in files:
            skill = frontmatter.load(str(f))

            # Fall back to the file name so a skill with missing
            # frontmatter still shows up as something loadable.
            name = skill.metadata.get("name") or f.stem
            description = skill.metadata.get("description") or "no description"

            result += f"\n- {name}: {description}"

        return result

    def get_toolset(self) -> FunctionToolset:
        """Expose the load_skill tool to the agent."""
        toolset = FunctionToolset()
        toolset.add_function(load_skill)

        return toolset

    async def before_tool_execute(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Log skill loads live, same as file actions are logged."""
        if call.tool_name == "load_skill":
            entry = f"loading skill: {args.get('skill_name')}"
            ctx.deps.console.log(entry)
            ctx.deps.events.append(entry)

        return args
