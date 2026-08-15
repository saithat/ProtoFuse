# Phillip TODO

Goal: paper → ordinary executable Proto → **one frozen reviewed program collection**
committed under `proto_programs/generated/<collection_id>/`.

Handoff runbook: [`workspaces/phillip/HANDOFF.md`](../../../workspaces/phillip/HANDOFF.md).

Sai chooses what to fuse, acceptable error rates, and final fusion behavior. Phillip
does not need to define end outputs or fusion acceptance criteria before handing off.

## Paper to programs (internal)

- [ ] Finish Paperclip/local-text ingestion with evidence and `unknowns`.
- [ ] Maintain a reviewed registry of allowed Proto components and typed parameters.
- [ ] Generate readable `design_*.py` from a reviewed `MethodologySpec`.
- [ ] Refuse source generation while any binding is unresolved.
- [ ] Validate allow-listed imports and confirm generated modules are inert on import.

## Handoff — commit a signed collection

Infrastructure is done; first real collection is not.

- [x] `finalize_collection()` validates `build_program()` without importing programs.
- [x] `collection.json` generation with stable metadata and SHA-256 hashes.
- [x] `load_collection()` path/hash/review checks (Sai's side).
- [ ] Generate `proto_programs/generated/dnachisel-num1/design_*.py` from NUM1 fixture
      (`program_builders.py`).
- [ ] Read generated source; confirm wiring matches
      `workspaces/phillip/fixtures/dnachisel-num1/methodology.json`.
- [ ] Run `finalize_collection(..., reviewed=True)` for collection ID `dnachisel-num1`.
- [ ] Commit `proto_programs/generated/dnachisel-num1/` to `main`.
- [ ] Tell Sai the collection ID: `dnachisel-num1`.

After Sai starts analysis, treat the collection as read-only. Any change → new
`collection_id`.

## Out of scope (Sai)

- Fusion target selection, surrogate design, and training.
- Error rates, uncertainty gates, and fallback policy.
- Defining final outputs or benchmark acceptance for fused paths.
- Writing into `data/analysis/`, `data/models/`, or `src/protofuse/sai/`.

## Workspace fixtures

Internal only — not the Sai handoff:

- `workspaces/phillip/fixtures/dnachisel-num1/methodology.json`
- `data/analysis/dnachisel-num1/` (ignored local profiles from prior runs)

Builder library: `program_builders.py`, `dnachisel_constraints.py`, `region_solver.py`.
