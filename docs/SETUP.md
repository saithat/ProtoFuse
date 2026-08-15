# Setup

## Local environment

ProtoFuse pins Python 3.12 because Proto currently documents Python 3.10+ and its
published classifiers cover through 3.12. The local machine's default Python can be
newer; `uv` creates the correct project environment.

```bash
uv sync --extra dev
cp .env.example .env
uv run pytest
uv run python examples/proto_smoke.py
uv run marimo edit workspaces/phillip/
```

The environment includes:

- Evo Design `proto-language`, pinned to a reviewed Git commit;
- `modal` for Proto's remote tools and other compute;
- Anthropic's Python SDK for the shared scientific agent;
- Pydantic for the versioned methodology contract;
- marimo for workspace notebooks (not Jupyter);
- pytest, Ruff, and mypy for shared-main safety.

Paperclip is installed separately because its current installer distributes and
authenticates the CLI, while `gxl-paperclip` is not currently available as a lockable
package from the Python package index.

## Authentication (each teammate does this locally)

1. Claim the relevant credits using the private event links in the organizer email.
2. Add `ANTHROPIC_API_KEY` to `.env`.
3. Create a Paperclip account and redeem the hackathon rate-limit offer. In your own
   terminal, run `curl -fsSL https://paperclip.gxl.ai/install.sh | bash`; its browser
   sign-in cannot be completed by an unattended project install. Alternatively, use
   Paperclip's hosted MCP server. For non-interactive scripts, put a dashboard-created
   `PAPERCLIP_API_KEY` in `.env`.
4. Run `uv run modal setup`. This opens a browser and stores credentials outside the
   repository.
5. If a chosen Proto component uses a gated model, accept that model's terms and add
   `HF_TOKEN` to `.env`.

Never paste credentials into source files, issues, commits, or experiment artifacts.

## Web-only partner tools

Phylo, Tamarind, and Benchling use their hosted account/workspace flows; they do not
require a repository dependency at this stage. Add an adapter only after the project
chooses a concrete API call. This keeps the base environment small and prevents
speculative integrations.
