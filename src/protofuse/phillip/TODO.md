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

Infrastructure is done; first real collection is not.

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
- [ ] Commit `proto_programs/generated/custom-egfp-lung/` to `main`.
- [ ] Tell Sai the collection ID: `custom-egfp-lung`.

After Sai starts analysis, treat the collection as read-only. Any change → new
`collection_id`.

## Candidate workflows (lower priority)

`dnachisel-num1` and `custom-egfp-lung` handoffs are complete on `main`. Wave 1 protein
workflows are implemented (`esm2-protein-maturation`, `antibody-cdr-maturation`) — see
[`docs/PROTEIN_WORKFLOW_SCAFFOLD.md`](../../../docs/PROTEIN_WORKFLOW_SCAFFOLD.md). Next wave:
FreeBindCraft binder, symmetric oligomer, PPI interface specificity. Full backlog in
[`docs/CANDIDATE_WORKFLOWS.md`](../../../docs/CANDIDATE_WORKFLOWS.md).

## Out of scope (Sai)

- Fusion target selection, surrogate design, and training.
- Error rates, uncertainty gates, and fallback policy.
- Defining final outputs or benchmark acceptance for fused paths.
- Writing into `data/analysis/`, `data/models/`, or `src/protofuse/sai/`.

## Workspace fixtures

Internal only — not the Sai handoff:

- `workspaces/phillip/fixtures/dnachisel-num1/methodology.json`
- `workspaces/phillip/fixtures/custom-egfp-lung/methodology.json`
- `workspaces/phillip/fixtures/esm2-protein-maturation/methodology.json`
- `workspaces/phillip/fixtures/antibody-cdr-maturation/methodology.json`
- `data/analysis/<collection_id>/` (ignored local Sai node profiles)
- `workspaces/phillip/PIPELINE_BENCHMARKS.json` (orchestrator wall times, all pipelines)

Builder library: `program_builders.py`, `dnachisel_constraints.py`, `region_solver.py`.
