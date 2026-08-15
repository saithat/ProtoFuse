# ProtoFuse

ProtoFuse lets a user write an ordinary Proto program and automatically applies reviewed
learned fusions when they are compatible and safe to use. Every other case stays on the
original full-model path.

```text
ordinary Proto program -> protofuse.optimize(program)
                              |
                    compatible registered fusion?
                        /                     \
                       no                     yes
                original program       selective router
                                        /           \
                                unsafe/uncertain    safe
                                  full models     surrogate
```

## Project layout

```text
src/protofuse/
├── program_collection.py   # sole Phillip -> Sai folder contract
├── runtime.py              # public automatic-fusion entry point
├── phillip/
│   ├── contracts.py        # MethodologySpec and ProtoPlan
│   ├── extractor.py        # paper -> MethodologySpec
│   ├── compiler.py         # MethodologySpec -> reviewed plan
│   ├── generator.py        # finalize generated Proto collections
│   └── pipeline.py         # paper -> Proto end to end
└── sai/
    ├── registry.py         # registered compatible fusions
    ├── optimizer.py        # program-level matching/transformation
    └── router.py           # uncertainty/OOD gate and full-model fallback

proto_programs/generated/   # frozen program collections Phillip gives Sai
data/                       # ignored papers, runs, training data, and weights
workspaces/phillip/          # disposable Phillip experiments
workspaces/sai/              # disposable Sai experiments
```

The only team artifact handoff is `proto_programs/generated/<collection_id>/`. There are
no graph dumps, scenario registries, or separate integration folders. `runtime.py` is the
product API, not another handoff directory.

## Runtime API

```python
from protofuse import optimize

program = build_program()
program = optimize(program)
results = program.run()
```

Until Sai registers a compatible `FusionBundle`, `optimize()` returns the original
program unchanged. A registered bundle installs a `SelectiveRouter` that uses its
surrogate only when the calibrated gate accepts the individual input.

## Setup

```bash
uv sync --extra dev
cp .env.example .env
uv run ruff check .
uv run mypy src/protofuse
uv run pytest
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/TEAM.md](docs/TEAM.md),
[docs/PROGRAM_COLLECTION.md](docs/PROGRAM_COLLECTION.md), and [docs/SETUP.md](docs/SETUP.md).

## Current state

Paper extraction and planning, collection manifest generation/hash validation, fusion
registration, automatic no-op fallback, and per-input fail-closed routing are implemented.
Phillip's Proto source generator and Sai's real program analyzer, trained surrogate, and
calibrated fusion bundle remain to be built.
