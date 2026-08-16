# Protein workflow scaffold

Shared conventions for adding GPU-backed protein workflows from
[`CANDIDATE_WORKFLOWS.md`](CANDIDATE_WORKFLOWS.md). Each workflow ends in a frozen
program collection under `proto_programs/generated/<scenario-id>/`.

## Prerequisites

- `dnachisel-num1` handoff complete (region-local MCMC template).
- Modal authenticated: `uv run modal setup` (required for GPU constraints at runtime).
- Verify tool keys before binding:

```bash
uv run python -m proto_tools.cli list | rg -i "esmfold|esm2|ablang|boltz2|rfdiffusion"
uv run python -m proto_language.cli list | rg -i "esm2|structure|protein|ablang|mcmc"
```

## Generate vs store run results

Two artifact types — do not conflate them:

| Artifact | What | Where | Committed? |
| --- | --- | --- | --- |
| **Frozen program collection** | Reviewed `design_*.py` + `collection.json` | `proto_programs/generated/<id>/` | Yes — Phillip handoff |
| **Run results** | Wall times, output summaries, node profiles | benchmarks / `data/analysis/` | Mixed |

### Generate frozen collections (Phillip handoff)

```bash
# Path A — generic handoff script (recommended)
uv run protofuse preflight <fixture-id> --length <smoke_length>
uv run python scripts/run_handoff_pipeline.py <fixture-id>

# Path B — CLI generate + manual finalize (legacy)
uv run protofuse generate <fixture-id>
# review design_*.py, then finalize via finalize_collection() API

# Validate
uv run protofuse collection validate <fixture-id>
uv run protofuse review <fixture-id>   # mechanical gate incl. PDB/hotspot binding
```

Handoff metadata (`methodology_id`, `seed_policy`, `compile_device`) lives in
[`src/protofuse/phillip/handoff_config.py`](../src/protofuse/phillip/handoff_config.py).
Timing output: `workspaces/phillip/TIMING_<fixture-id>.json`.

GPCR with paper ingest: `uv run python scripts/run_gpcr_cxcr4_pipeline.py`.

Contract: [`docs/PROGRAM_COLLECTION.md`](PROGRAM_COLLECTION.md),
[`workspaces/phillip/HANDOFF.md`](../workspaces/phillip/HANDOFF.md).

### Store run results (execution)

`protofuse run` prints to stdout only — it does **not** persist results.

| Storage | Writer | Committed? |
| --- | --- | --- |
| [`PIPELINE_BENCHMARKS.json`](../workspaces/phillip/PIPELINE_BENCHMARKS.json) | `scripts/benchmark_pipelines.py` | Yes — orchestrator wall times |
| `workspaces/phillip/TIMING_<id>.json` | `run_handoff_pipeline.py` | Optional — generation timing |
| `data/analysis/<collection_id>/` | Sai (not built) | No — gitignored node profiles |
| `data/models/` | Sai (not built) | No — gitignored surrogate weights |

After adding a workflow, extend `benchmark_pipelines.py` with preflight, handoff, compile,
and Modal `execute_smoke` runs, then:

```bash
uv run python scripts/benchmark_pipelines.py --skip-full
uv run python scripts/benchmark_pipelines.py --skip-modal-exec   # CPU + handoff only
```

## Per-workflow checklist

1. `workspaces/phillip/fixtures/<scenario-id>/methodology.json` + `README.md`
2. Entry in [`handoff_config.py`](../src/protofuse/phillip/handoff_config.py)
3. Registry block in `src/protofuse/phillip/registries.py`
4. Builder in `src/protofuse/phillip/program_builders.py` (or dedicated module)
5. Smoke/full tier params in `resolve_workload_params()` + `WORKLOAD_PROFILES`
6. `uv run protofuse preflight <scenario-id> --length <smoke_length>`
7. `uv run python scripts/run_handoff_pipeline.py <scenario-id>`
8. Test: `tests/test_<scenario-id>.py` + collection hash test
9. Integration: CLI `FIXTURE_CHOICES`, `catalog.json`, benchmark block
10. Integration agent updates CLI `choices=` and `catalog.json`

## Topology templates

| Topology | Reference workflow | Builder pattern |
| --- | --- | --- |
| `iterative_refinement` | `dnachisel-num1` | `run_region_local_program` + MCMC |
| `propose_score_select` | `custom-egfp-lung` | `run_pool_optimizer` |
| `staged_filter` | `gpcr-cxcr4-miniprotein` | `RejectionSamplingOptimizer` |
| `cycling` | (new) | dedicated `cycling_builders.py` module |

## Smoke / full tier conventions

| Workflow | Smoke | Full |
| --- | --- | --- |
| `esm2-protein-maturation` | 50 steps, 80 aa GFP | 200 steps, 129 aa lysozyme |
| `antibody-cdr-maturation` | 30 steps, 1 CDR region | 100 steps, 3 CDR regions |
| `freebindcraft-binder` | 5 samples | 50 samples |
| `rfdiffusion3-boltz2-binder` | 2 cycles | 10 cycles |
| `gpcr-cxcr4-miniprotein` | 2 samples, 40 aa | 10 samples, 70 aa |

## Allowed imports in generated `design_*.py`

- `proto_language.core` (Program, Segment, Construct, Constraint)
- `protofuse.phillip.program_builders` (load_fixture_spec, resolve_workload_params, build_*)
- No Modal, network, or model loading on import.

## Wave execution plan

| Wave | Workflows | Parallelism |
| --- | --- | --- |
| 1 | `esm2-protein-maturation`, `antibody-cdr-maturation` | Done |
| 2 | `freebindcraft-binder`, `symmetric-oligomer-ring`, `ppi-interface-specificity` | Done |
| 3 | `rfdiffusion3-boltz2-binder`, `ligandmpnn-enzyme-redesign`, `bioemu-ensemble-filter` | 3 agents |

`gpcr-cxcr4-miniprotein` overlaps Wave 2/3 binder work — use it as the RFdiffusion3+Boltz-2
reference instead of duplicating.

## Sai handoff

Phillip stops at frozen collection + collection ID. Do not edit `src/protofuse/sai/`.
Sai writes node profiles to gitignored `data/analysis/<collection_id>/`.
