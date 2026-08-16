# Phillip TODO

Goal: paper → ordinary executable Proto → **one frozen reviewed program collection**
committed under `proto_programs/generated/<collection_id>/`.

Handoff runbook: [`workspaces/phillip/HANDOFF.md`](../../../workspaces/phillip/HANDOFF.md).

**Pipeline timings (local + Modal):** [`workspaces/phillip/PIPELINE_BENCHMARKS.md`](../../../workspaces/phillip/PIPELINE_BENCHMARKS.md)
· re-run `uv run python scripts/benchmark_pipelines.py`.

Sai chooses what to fuse, acceptable error rates, and final fusion behavior. Phillip
does not need to define end outputs or fusion acceptance criteria before handing off.

## Paper to programs (internal)

- [ ] Finish Paperclip/local-text ingestion with evidence and `unknowns`.
- [x] Maintain a reviewed registry of allowed Proto components and typed parameters.
- [x] Generate readable `design_*.py` from a reviewed `MethodologySpec`.
- [x] Refuse source generation while any binding is unresolved.
- [x] Validate allow-listed imports and confirm generated modules are inert on import.

## Handoff — commit a signed collection

The handoff infrastructure and 12 reviewed collections are committed. A generated folder
is not automatically a handoff: `rfdiffusion3-af3-ppi`, `af3-boltz2-state-sweep`, and
`evo2-enformer-borzoi` currently remain `reviewed=false` pending human scientific review.

- [x] `finalize_collection()` validates `build_program()` without importing programs.
- [x] `collection.json` generation with stable metadata and SHA-256 hashes.
- [x] `load_collection()` path/hash/review checks (Sai's side).
- [x] Generate `proto_programs/generated/dnachisel-num1/design_*.py` from NUM1 fixture
      (`program_builders.py`).
- [x] Read generated source; confirm wiring matches
      `workspaces/phillip/fixtures/dnachisel-num1/methodology.json`.
- [x] Run `finalize_collection(..., reviewed=True)` for collection ID `dnachisel-num1`.
- [x] Commit `proto_programs/generated/dnachisel-num1/` to `main`.
- [x] Tell Sai the collection ID: `dnachisel-num1`.

- [x] Generate `proto_programs/generated/custom-egfp-lung/design_*.py` from CUSTOM fixture.
- [x] Run `finalize_collection(..., reviewed=True)` for collection ID `custom-egfp-lung`.
- [x] Commit `proto_programs/generated/custom-egfp-lung/` to `main`.
- [x] Tell Sai the collection ID: `custom-egfp-lung`.

After Sai starts analysis, treat the collection as read-only. Any change → new
`collection_id`.

## Candidate workflows and review queue

The reviewed corpus now includes both DNA handoffs and ten protein workflows, including
`boltz2-state-sweep`, RFdiffusion3 + Boltz-2 cycling, LigandMPNN enzyme redesign, and
BioEmu ensemble filtering. See
[`docs/PROTEIN_WORKFLOW_SCAFFOLD.md`](../../../docs/PROTEIN_WORKFLOW_SCAFFOLD.md).

The next handoff work is not more builder plumbing. It is human paper-encoding review for
the three `reviewed=false` joint-objective collections named above, followed by normal
finalization if accepted. Unbuilt ideas such as `tm-switch-multistate` remain in
[`docs/CANDIDATE_WORKFLOWS.md`](../../../docs/CANDIDATE_WORKFLOWS.md).

## Out of scope (Sai)

- Fusion target selection, surrogate design, and training.
- Error rates, uncertainty gates, and fallback policy.
- Defining final outputs or benchmark acceptance for fused paths.
- Writing into `data/analysis/`, `data/models/`, or `src/protofuse/sai/`.

## Workspace fixtures

Internal only — not the Sai handoff:

- `workspaces/phillip/fixtures/<fixture-id>/methodology.json`
- `data/analysis/<collection_id>/` (ignored local Sai node profiles)
- `workspaces/phillip/PIPELINE_BENCHMARKS.json` (orchestrator wall times, all pipelines)

Builder library: `program_builders.py`, `dnachisel_constraints.py`, `region_solver.py`.
