# Setup

## Local environment

```bash
uv sync --extra dev
cp .env.example .env
uv run ruff check .
uv run mypy src/protofuse
uv run pytest
```

The environment includes pinned Proto Language, Modal, Anthropic's Python SDK, Pydantic,
NumPy for the portable linear-ensemble baseline, pytest, Ruff, and mypy. Heavier learned-model
libraries remain intentionally absent until a reviewed experiment requires them.

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

## Resumable runs

Reviewed fixture runs checkpoint automatically under `data/runs/checkpoints/`:

```bash
uv run protofuse run esm2-protein-maturation --tier full
```

If a model provider reports exhausted credits, a rate limit, or another failure, rerun the
same command after restoring access. ProtoFuse validates that the rebuilt program matches
the saved fingerprint, restores the last completed optimizer unit, and retries only the
in-flight unit. A unit is one MCMC step, one cycling round, or one rejection-sampling
proposal batch (because proposals in that batch share a single model call).

Useful controls:

```bash
# Store checkpoints elsewhere (the path must persist between attempts).
uv run protofuse run esm2-protein-maturation --tier full \
  --checkpoint-dir /path/to/persistent/checkpoints

# Archive the saved fixture/tier run and deliberately start from zero.
uv run protofuse run esm2-protein-maturation --tier full --restart

# Run without checkpointing for a short disposable check.
uv run protofuse run esm2-protein-maturation --tier smoke --no-checkpoint
```

Checkpoint writes use strict JSON plus atomic file replacement; they never use executable
pickle data. Manifests record attempt status, cumulative observed wall time, resume count,
and redacted failure text. Program files contain sequence and optimizer/RNG state, while an
append-only trace records completed-boundary energy summaries and sequence hashes. These files
remain outside Git through the existing `data/runs/*` ignore rule.

The normal CLI remains local even when GPU-backed Proto tools are dispatched to Modal, so
the default checkpoint directory persists on the calling machine. If the orchestrator itself
runs in an ephemeral cloud container, pass `--checkpoint-dir` on a persistent mounted volume.

## Fusion development workflow

Use manifest program IDs such as `design-001`; the filename `design_001.py` is only a stable
ordinal. In the common two-program collections, `design-001` is the full workload and
`design-002` is the smoke workload, but always confirm the tier in the generated module
docstring rather than inferring it from the number.

```bash
# Inspect an exact program signature without running the model workload.
uv run protofuse analyze \
  proto_programs/generated/<collection-id> <program-id>

# Collect append-only parent outputs. Use distinct group IDs for leakage-resistant splits.
uv run protofuse trace \
  proto_programs/generated/<collection-id> <program-id> \
  --out data/analysis/<collection-id>/teacher.jsonl \
  --run-id <run-id> --group-id <target-or-campaign-id> --tier full

# Summarize the actual calls, then train the portable multi-output baseline.
uv run protofuse fusion profile \
  --trace data/analysis/<collection-id>/teacher.jsonl \
  --out data/analysis/<collection-id>/profile.json
uv run protofuse fusion train \
  proto_programs/generated/<collection-id> <program-id> \
  --trace data/analysis/<collection-id>/teacher.jsonl \
  --optimizer-index 0 --constraint <label-a> --constraint <label-b> \
  --fusion-id <fusion-id> --version 1 --out data/models/<fusion-id>
```

Training artifacts always start with `reviewed=false`. The following flags are for local
development only; the normal validation and evaluation commands reject unreviewed artifacts:

```bash
uv run protofuse fusion validate data/models/<fusion-id> --allow-unreviewed
uv run protofuse fusion evaluate \
  data/models/<fusion-id> proto_programs/generated/<collection-id> <program-id> \
  --seed 1 --seed 2 --allow-unreviewed
```

After human review explicitly changes the manifest status, `protofuse.optimize()` lazily
discovers hash-valid bundles under `data/models/`. Set `PROTOFUSE_BUNDLE_DIR` to use a
different artifact root. No model artifact in the repository is currently reviewed.
