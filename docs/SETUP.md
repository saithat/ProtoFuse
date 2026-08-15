# Setup

## Local environment

```bash
uv sync --extra dev
cp .env.example .env
uv run ruff check .
uv run pytest
```

The environment includes pinned Proto Language, Modal, Anthropic's Python SDK, Pydantic,
pytest, Ruff, and mypy. Add learned-fusion training libraries only after Sai selects a
surrogate family; this avoids committing speculative GPU dependencies.

## Authentication

Each teammate completes account authentication locally:

1. Claim the relevant organizer credits from the private event email.
2. Put `ANTHROPIC_API_KEY` in `.env`.
3. Create and authenticate a Paperclip account if using it for paper access. In your own
   terminal, run `curl -fsSL https://paperclip.gxl.ai/install.sh | bash`; its browser
   sign-in cannot be completed by an unattended project install. Alternatively, use
   Paperclip's hosted MCP server. For non-interactive scripts, put a dashboard-created
   `PAPERCLIP_API_KEY` in `.env`.
4. Run `uv run modal setup` only when a selected Proto component needs Modal compute.
5. Add `HF_TOKEN` only when a selected model requires it.

Never paste credentials into source files, commits, issues, or experiment artifacts.

Phylo, Tamarind, and Benchling are hosted tools and need no repository dependency until
the project chooses a concrete API integration.
