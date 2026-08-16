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
    ├── analyzer.py         # controlled reviewed-program loading
    ├── signatures.py       # exact Proto component signatures
    ├── tracing.py          # append-only parent-output traces
    ├── training.py         # grouped multi-output baseline and calibration
    ├── artifacts.py        # safe JSON model manifests and discovery
    ├── transform.py        # transactional replacement plus parent validation
    └── router.py           # uncertainty/OOD gate and full-model fallback

proto_programs/generated/   # frozen program collections Phillip gives Sai
data/                       # ignored papers, runs, training data, and weights
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

Until a compatible reviewed `FusionBundle` is registered or discovered, `optimize()`
returns the original program unchanged. By default the runtime lazily checks
`data/models/`, or `PROTOFUSE_BUNDLE_DIR` when configured, and accepts only hash-valid
artifacts marked `reviewed=true`. An accepted bundle installs a `SelectiveRouter` that
uses its surrogate only when the calibrated gate accepts the individual input.

The implementation workflow is available from the CLI:

```bash
protofuse analyze proto_programs/generated/<collection> <program-id>
protofuse trace proto_programs/generated/<collection> <program-id> \
  --out data/analysis/<collection>/teacher.jsonl --run-id <run> \
  --group-id <split-group> --seed <seed>
protofuse fusion profile --trace data/analysis/<collection>/teacher.jsonl
protofuse fusion compare-models \
  --trace data/analysis/<collection>/teacher.jsonl --optimizer-index 0 \
  --constraint <objective-a> --constraint <objective-b> \
  --out data/analysis/<collection>/model-comparison.json
protofuse fusion train proto_programs/generated/<collection> <program-id> \
  --trace data/analysis/<collection>/teacher.jsonl --optimizer-index 0 \
  --constraint <objective-a> --constraint <objective-b> \
  --fusion-id <id> --version 1 --out data/models/<id>
protofuse fusion evaluate data/models/<id> \
  proto_programs/generated/<collection> <program-id> \
  --seed 1 --seed 2 --allow-unreviewed \
  --out data/analysis/<collection>/paired-evaluation.json
```

Training deliberately writes `reviewed=false`. A generated model is not auto-registered
until its scientific interpretation, calibration thresholds, and paired evaluation have
been reviewed and that status is explicitly changed in its manifest.

The current baseline is **multi-output, not scalarized**: one artifact predicts a vector of
ordinary Proto constraint scores and routes that group together. Its linear output columns do
not explicitly learn covariance between objectives. Here, “joint” means aligned teacher data,
one inference call, and one fail-closed routing decision—not one weighted objective and not a
covariance-aware multi-task model.

`compare-models` is an offline audit of the current linear ensemble, Extra Trees, and a small
shared-trunk MLP on one frozen grouped split. It never packages a model or declares a winner.
Runtime artifacts remain linear-only until a reviewed comparison justifies extending the artifact
format and router.

The paired evaluator is the only timed experiment path. Warmup runs are reported but
excluded, measured arm order is counterbalanced, and non-finite Proto sentinel energies are
recorded as invalid outcomes rather than numeric errors.

## Setup

```bash
uv sync --extra dev
cp .env.example .env
uv run ruff check .
uv run mypy src/protofuse
uv run pytest
```

During fusion-experiment development, `uv run pytest tests/test_sai_pipeline.py
tests/test_model_comparison.py` is the fast inner loop. The full suite includes a minute-scale
workload test and is required only at the pre-push gate.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/TEAM.md](docs/TEAM.md),
[docs/PROGRAM_COLLECTION.md](docs/PROGRAM_COLLECTION.md), and [docs/SETUP.md](docs/SETUP.md).

### Inspect a run while it is executing

By default, `protofuse run` prints both its checkpoint directory and the path to `events.jsonl`
before model execution begins. The event log is append-only and records the run, program, and
stage lifecycle; every optimizer progress callback; checkpoint decisions; timings; energy
scores; result hashes; resume activity; and redacted failures. Follow it from another terminal:

```bash
tail -f data/runs/checkpoints/<fixture>/<tier>/events.jsonl
```

The sibling `manifest.json` and `program-*.json` files contain the latest resumable state, while
`program-*.trace.jsonl` contains the compact per-checkpoint history. Raw sequences are not written
to the operational event log. `protofuse trace --hash-inputs-only` provides the separate,
proposal-level scientific trace without recording raw input sequences.
Passing `--no-checkpoint` explicitly disables both resumable state and this event stream.

## Portable evaluation report

The paired-evaluation JSON above is the canonical scientific result. The self-contained HTML
report is a presentation snapshot of the aggregate evidence available when it was generated; it
does not replace the paired result and does not require ChatGPT, npm, or a web server:

```bash
python3 scripts/build_visualization_bundle.py --strict
python3 scripts/build_evaluation_report.py
open reports/protofuse-evaluation.html  # macOS; or double-click the file
```

The visualization builder exports reviewed final sequences, attached structures, score vectors,
and provenance from ignored raw results into the tracked `data/visualizations/` bundle. The report
generator reads that bundle plus aggregate artifacts from `data/analysis/`, optional checkpoints
from `data/runs/checkpoints/`, and methodology provenance from `workspaces/phillip/fixtures/`.
It excludes proposal pools and teacher traces while embedding the curated final candidates and
normalized aggregate JSON. See [reports/README.md](reports/README.md).

## Current state

Paper extraction and planning, Proto source generation, collection validation, controlled
analysis, exact matching, tracing/profiling, grouped baseline training, safe artifact loading,
transactional transformation, per-input fallback, and final parent validation are implemented.
No repository model is currently marked as a reviewed fusion: collecting real teacher traces,
choosing scientific error thresholds, running paired full-versus-fused evaluation, and approving
the first artifact remain experiment/review work rather than missing application code.
