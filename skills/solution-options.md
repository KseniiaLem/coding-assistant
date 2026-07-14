---
name: solution-options
description: Load this skill when a coding task can be solved in more than one reasonable way, before implementing anything.
---

When a task has several viable approaches, do not pick one silently.
Present exactly three options first, then let the user choose.

For each option provide:

1. **A short name** (e.g., "Standard library only", "With a database",
   "Quick script").
2. **The core idea** in one or two sentences.
3. **A minimal code sketch** — 5 to 15 lines showing the shape of the
   solution, not the full implementation.
4. **Trade-offs**: simplicity, performance, maintainability, and
   external dependencies. Be honest about the weaknesses of each.
5. **When to choose it** in one sentence.

Rules:

* End with a recommendation: name ONE option and give the reason.
* Wait for the user's choice before implementing, unless the user
  explicitly asked you to decide yourself.
* The three options must be genuinely different approaches, not three
  variations of the same idea.
* If the task truly has only one reasonable solution, say so and
  explain why alternatives would be artificial.
