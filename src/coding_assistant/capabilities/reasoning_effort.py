"""Reasoning-effort switch driven by @low / @high tags in the prompt."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings


@dataclass
class ReasoningEffort(AbstractCapability[Any]):
    """Select reasoning effort from @low / @high tags in the prompt.

    No tag means the provider default (medium) is used.
    """

    def get_model_settings(
        self,
    ) -> Callable[[RunContext[Any]], ModelSettings]:
        """Return the per-run settings hook that reads the tags."""

        def _set_reasoning_effort(ctx: RunContext[Any]) -> ModelSettings:
            user_prompt = str(ctx.prompt)

            # Word-boundary match: react to the "@low" tag itself, not to
            # substrings like "@lowest" or an email address containing it.
            if re.search(r"(?<!\w)@low\b", user_prompt):
                return ModelSettings(thinking="low")
            if re.search(r"(?<!\w)@high\b", user_prompt):
                return ModelSettings(thinking="high")

            return ModelSettings()

        return _set_reasoning_effort
