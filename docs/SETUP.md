# Setup

## Local environment

```bash
uv sync --extra dev
cp .env.example .env
uv run ruff check .
uv run mypy src/protofuse
uv run pytest
```

For fusion-experiment edits, use `uv run pytest tests/test_sai_pipeline.py
tests/test_model_comparison.py` as the fast inner loop. Use `uv run pytest -m "not slow"` for the
broader suite, and run the command above once before pushing to `main`; it includes the
intentionally minute-scale full DNAChisel workload.

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
4. For Modal GPU tools, either run `uv run modal setup` **or** put service-user tokens in `.env`:
   `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, and `MODAL_ENVIRONMENT=main` (see `.env.example`).
   Add a payment method at [modal.com/settings/billing](https://modal.com/settings/billing) before deploying H100 apps.
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
  --run-id trajectory-seed-<seed> --group-id trajectory-seed-<seed> \
  --seed <seed> --tier full

# Summarize the actual calls and compare compact model families on one frozen split.
uv run protofuse fusion profile \
  --trace data/analysis/<collection-id>/teacher.jsonl \
  --out data/analysis/<collection-id>/profile.json
uv run protofuse fusion compare-models \
  --trace data/analysis/<collection-id>/teacher.jsonl \
  --optimizer-index 0 --constraint <label-a> --constraint <label-b> \
  --out data/analysis/<collection-id>/model-comparison.json

# Package the currently supported portable linear baseline only after reviewing that report.
uv run protofuse fusion train \
  proto_programs/generated/<collection-id> <program-id> \
  --trace data/analysis/<collection-id>/teacher.jsonl \
  --optimizer-index 0 --constraint <label-a> --constraint <label-b> \
  --fusion-id <fusion-id> --version 1 --out data/models/<fusion-id>
```

The comparison command fits a bootstrap linear ensemble, Extra Trees, and a small multi-output
MLP using the identical grouped train/calibration/audit split. It warms each fitted predictor
before measuring inference latency and records no automatic winner. It is an offline audit only:
`fusion train` and runtime artifacts remain linear until a reviewed result justifies another
artifact format.

One `trace` invocation creates one seeded optimizer trajectory. That trajectory can contribute
many aligned proposal-level teacher samples, but every one of those samples must keep the same
`group-id` and stay in the same split. For example, ten 20-step trajectories create about 200
aligned teacher samples; the current 60/20/20 group split produces six/two/two independent
trajectory groups and about 120/40/40 proposal samples. The effective independent counts are
six/two/two, not 120/40/40.

For the next single-program experiment, target 60 training, 20 calibration, and 20 untouched test
trajectories. Use approximately 50 additional unseen seeds for the paired runtime experiment and
40--60 deliberately designed challenge cases. See `docs/EVALUATION.md` for the rationale and
stopping rules.

The repository does not yet provide a resumable multi-seed trace campaign command. `trace` runs
one program directly, while `protofuse run` is the command currently connected to checkpoint
sessions. Do not launch a large expensive campaign until trace collection has campaign-level
planning, resume/deduplication, a frozen external-test manifest, and a dry-run check for the chosen
score-only constraint group.

Training artifacts always start with `reviewed=false`. The following flags are for local
development only; the normal validation and evaluation commands reject unreviewed artifacts:

```bash
uv run protofuse fusion validate data/models/<fusion-id> --allow-unreviewed
uv run protofuse fusion evaluate \
  data/models/<fusion-id> proto_programs/generated/<collection-id> <program-id> \
  --seed 1 --seed 2 --allow-unreviewed \
  --out data/analysis/<collection-id>/paired-evaluation.json
```

This is the single timed experiment path. It performs an excluded warmup pair, alternates
which arm runs first, and writes the complete warm-runtime, final-accuracy, routing, and
reliability report. Use `--no-warmup` only for a quick diagnostic where startup effects are
acceptable.

After human review explicitly changes the manifest status, `protofuse.optimize()` lazily
discovers hash-valid bundles under `data/models/`. Set `PROTOFUSE_BUNDLE_DIR` to use a
different artifact root. No model artifact in the repository is currently reviewed.

## Hackathon progress notebook

Read-only GXL demo dashboard built from collection manifests, benchmark JSON, and git history:

```bash
uv sync --extra notebook
uv run marimo run notebooks/hackathon_progress.py    # app view — no code cells
# or
uv run marimo edit notebooks/hackathon_progress.py   # editor with visible code
```

Export static HTML for judges:

```bash
uv run marimo export html notebooks/hackathon_progress.py -o notebooks/hackathon_progress.html
```
