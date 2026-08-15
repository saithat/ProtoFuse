# ProtoFuse

ProtoFuse has one simple research handoff:

```text
paper -> scientific agent -> Phillip's paper-to-Proto pipeline
      -> proto_programs/generated/<collection_id>/
      -> Sai's selective learned fusion
      -> Phillip's final end-to-end run
```

Phillip owns everything from a paper through saved, executable Proto programs. Sai reads
those programs, finds recurring expensive model-step groups, and develops a surrogate
that defers uncertain or out-of-domain inputs to the original full models.

## Project layout

```text
src/protofuse/
├── scientific_agent/   # shared evidence-grounded extraction
├── phillip/             # paper -> MethodologySpec -> Proto programs -> final E2E
├── sai/                 # profiling, learned fusion, uncertainty, and deferral
└── contracts.py         # shared MethodologySpec

proto_programs/generated/  # the Phillip -> Sai handoff
data/                      # ignored papers, runs, training data, and weights
workspaces/phillip/         # disposable Phillip experiments
workspaces/sai/             # disposable Sai experiments
```

There are only two code integration points:

1. Phillip freezes a generated-program folder for Sai.
2. Sai exposes one selective-fusion callable that Phillip uses in the final E2E run.

See [docs/TEAM.md](docs/TEAM.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and
[docs/PROGRAM_COLLECTION.md](docs/PROGRAM_COLLECTION.md).

## Setup

```bash
uv sync --extra dev
cp .env.example .env
uv run ruff check .
uv run pytest
```

After configuring Anthropic, extract a local paper text file with:

```bash
uv run protofuse extract path/to/paper.txt --out data/specs/paper.json
```

Account authentication is separate from package installation. See
[docs/SETUP.md](docs/SETUP.md).

## Current state

The shared methodology contract, scientific-agent adapter, safe component planning, and
Phillip-owned topology selection are implemented. Phillip's collection generator and
Sai's learned-fusion implementation are the next milestones.
