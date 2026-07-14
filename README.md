# Coding Assistant

A simple but functional agentic AI coding assistant built with [Pydantic AI](https://ai.pydantic.dev/) and FastAPI.

It accepts coding tasks in natural language, decides which tools to use, safely reads and modifies files inside an isolated workspace, and reports its actions through either a terminal or web interface.

The project was originally created as part of the THRIVE Machine Learning Specialization masterclass by the appliedAI Institute for Europe. It was subsequently expanded with additional security, reliability, planning, and user-interface features.

## What it does

The assistant can:

* hold multi-turn conversations using message history
* read, write, search, and delete files inside a sandboxed folder
* show file operations in real time through execution hooks
* adjust reasoning effort for individual requests
* explore a solution without modifying files in planning mode
* explain created or modified code in plain language
* load Markdown skill files at runtime to extend its behavior
* recover from API and network failures without losing the conversation
* cancel an active request without ending the session

The agent works only with files inside the `sandbox/` folder.

## Requirements

* Python
* [uv](https://docs.astral.sh/uv/)
* an OpenRouter API key
* access to the model configured in the `.env` file

API usage may incur costs depending on the selected model and OpenRouter pricing.

## Setup

1. Install [uv](https://docs.astral.sh/uv/).

2. Clone this repository and open the project folder.

3. Install the project dependencies:

   ```bash
   uv sync
   ```

4. Create a `.env` file in the project root:

   ```env
   OPENAI_API_BASE=https://openrouter.ai/api/v1
   OPENAI_API_KEY=your-openrouter-key
   MODEL=openai/gpt-5.1-codex-mini
   ```

The `.env` file is excluded from Git. API keys and other secrets must never be committed to the repository.

## Run

### Terminal interface

```bash
uv run coding-assistant
```

Available session commands:

* `/new` — start a new conversation
* `/help` — show available commands
* `/plan` — enable planning mode
* `exit` — close the session

Add `@low` or `@high` to a request to override the reasoning effort for that request.

Token usage is displayed after each answer.

Press `Ctrl+C` while a request is running to cancel only the active request. The terminal session remains open and the conversation history is preserved.

### Web interface

```bash
uv run coding-assistant-web
```

Then open:

```text
http://127.0.0.1:8000
```

The web interface includes:

* two color themes: night and wine
* a minimal six-token color palette
* an in-memory conversation history panel
* a live activity log showing file operations
* low, medium, and high reasoning-effort settings
* planning-mode and extended-explanation controls
* a Stop button that replaces Send while the agent is working
* an **allow delete** control for explicit deletion consent

The Stop button cancels the active request without ending the conversation.

Conversation history is stored in memory and is cleared when the server restarts.

The browser cannot display an interactive `y/N` confirmation while an agent request is running. For this reason, file deletion is refused unless the **allow delete** control is enabled before the request is sent.

## Project structure

```text
src/coding_assistant/
├── main.py                      # terminal conversation loop and agent configuration
├── web.py                       # FastAPI web interface
├── deps.py                      # dependencies injected into each agent run
└── capabilities/
    ├── file_operations.py       # sandboxed file tools and activity logging
    ├── reasoning_effort.py      # per-request reasoning-effort controls
    └── skills.py                # runtime Markdown skill loader

skills/                          # Markdown skill files loaded by the agent
sandbox/                         # isolated workspace available to the agent
```

## Improvements over the masterclass template

The original masterclass project provided the basic agent structure. The following features and safeguards were added as extensions.

### Security

* **Path-traversal protection**

  Paths such as `../.env` are rejected instead of being allowed to escape the sandbox. The same validation is applied to the runtime skills loader.

* **Safe file search**

  Glob patterns such as `../*` can no longer expose files outside the sandbox. Search results are resolved and filtered before they are returned to the agent.

* **Human-in-the-loop deletion**

  The agent cannot delete files without explicit consent. The terminal requests confirmation through a `y/N` prompt, while the web interface requires the **allow delete** control to be enabled.

* **Sanitized chat rendering**

  Model output is treated as untrusted content. Because text read from a file could contain malicious HTML, web responses are sanitized with DOMPurify before being rendered.

* **Mechanically enforced planning mode**

  Planning mode does not rely only on prompt instructions. File writes and deletions are blocked directly at the tool level while the mode is active.

### Reliability

* **Errors returned as data**

  Missing files, invalid paths, and rejected operations are returned to the model as structured error messages. The agent can respond to the problem and correct its approach instead of terminating the session.

* **Resilient conversations**

  API and network failures do not destroy the active conversation. Message history is preserved so the user can retry the request.

* **Cancellable requests**

  Each request runs as a separate `asyncio.Task` and can be cancelled without ending the session.

  In the terminal, `Ctrl+C` cancels the current task. In the web interface, the Stop button calls a server-side `/chat/{id}/stop` endpoint.

* **UTF-8 file handling**

  File operations use explicit UTF-8 encoding, preventing Windows `charmap` errors encountered during testing.

* **Isolated request dependencies**

  Each web request receives its own agent dependencies, preventing concurrent conversations from sharing mutable request state.

### Agent behavior

* **Adjustable reasoning effort**

  Reasoning effort can be controlled for individual requests. The terminal supports `@low` and `@high` request tags, while the web interface provides low, medium, and high settings.

* **Planning mode**

  The agent can inspect a task and propose a design before making changes. While planning mode is active, file modification tools are disabled.

* **Extended code explanations**

  The agent comments non-obvious code and provides a plain-language walkthrough after creating or changing files.

* **Runtime skills**

  New behaviors can be added through Markdown skill files without modifying the Python source code.

  Included skills:

  * `architecture-design` — requires design-first reasoning and approval before multi-file implementation
  * `solution-options` — presents three distinct approaches, sketches their structure, and recommends one

### User interface

* **Terminal session commands**

  The terminal interface supports `/new`, `/help`, `/plan`, and `exit`.

* **Token visibility**

  Token usage is displayed after every answer.

* **Web interface**

  The FastAPI interface provides conversation history, live activity logging, themes, reasoning controls, planning mode, extended explanations, cancellation, and deletion consent.

* **Live execution feedback**

  File operations are recorded through execution hooks and shown in the activity panel while the agent is working.

## Safety model

The project uses several independent layers of protection:

1. The agent receives instructions describing the allowed workspace.
2. File paths are resolved and validated before every operation.
3. Search results outside the sandbox are removed.
4. Planning mode blocks mutating tools in code.
5. File deletion requires explicit user consent.
6. Model-generated HTML is sanitized before browser rendering.

These protections reduce the risk of prompt injection, accidental file access, unsafe deletion, and malicious content being rendered in the web interface.

## Notes

* The agent can access only the `sandbox/` directory.
* Web conversation history is not persisted between server restarts.
* API keys must remain in the local `.env` file.
* API requests may generate costs through OpenRouter.
* Planning mode prevents file writes and deletions but still allows the agent to inspect the available project files.


