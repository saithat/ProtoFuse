# Phillip TODO

Primary goal: own the paper-to-Proto pipeline and generate a reviewed directory of Proto
program files that Sai can analyze without additional graph or profiling work from
Phillip.

## Paper to methodology

- [ ] Add a Paperclip or local-text ingestion adapter that records a paper identifier
  without committing paper contents.
- [ ] Produce a validated `MethodologySpec` with evidence, assumptions, and `unknowns`.
- [ ] Keep extraction, validation, binding, generation, and execution failures distinct.

## Proto program generation

- [ ] Maintain a reviewed registry of allowed `proto_language` components and typed
  configuration fields.
- [ ] Keep a design non-executable while any component, parameter, or model binding is
  unresolved.
- [ ] Add one command that generates
  `proto_programs/generated/<collection_id>/` from a paper or validated specification.
- [ ] Generate one or more readable `design_<id>.py` files, each exposing
  `build_program()` and performing no work on import.
- [ ] Automatically generate `collection.json` with program hashes, entry points, pinned
  Proto/registry versions, input roles, seed policy, source-spec IDs, and review status.
- [ ] Use stable local names and explicit construction order so Sai's scanner and an LLM
  can understand each design.
- [ ] Never emit code, commands, imports, URLs, or unreviewed model identifiers copied
  from paper text.
- [ ] Keep raw paper content, confidential sequences, credentials, and generated run
  outputs out of the collection directory.

## Collection validation and handoff

- [ ] Validate all file hashes and allow-listed imports before execution.
- [ ] Import every design without triggering model loading, network calls, or execution.
- [ ] Smoke-run every reviewed `build_program()` using the pinned Proto dependency and a
  synthetic or authorized input.
- [ ] Provide representative input roles and optional redistributable examples; Sai owns
  profiling inputs beyond this smoke test.
- [ ] Freeze the collection directory before Sai begins profiling or teacher-data
  generation.
- [ ] Notify Sai of the collection path and ID. No separate graph/profile bundle is
  required.

## Intermediate decisions

- [ ] **Check-in 0 — methodology:** Both approve evidence, assumptions, and unknowns.
- [ ] **Check-in 1 — collection freeze:** Both approve registry bindings, generated
  source, manifest hashes, and executable-safety status.
- [ ] **Decision 1 — fusion target:** Sai presents a measured recurring step group; both
  approve its inputs, joint outputs, thresholds, and asymmetric error costs.
- [ ] **Decision 2 — operating point:** Both choose a risk/coverage threshold or reject
  the surrogate experiment.
- [ ] **Check-in 2 — integration:** Phillip verifies full-model fallback and final
  validation in the complete paper-to-workflow run.

## Integration checks

- [ ] Confirm identical methodology, registry, and configuration inputs produce the same
  collection files and hashes.
- [ ] Confirm malformed or unresolved designs fail before source generation or execution.
- [ ] Confirm generated source contains only allow-listed imports and registry symbols.
- [ ] Confirm every program exposes `build_program()` and is inert on import.
- [ ] Confirm Sai can analyze a frozen collection without Phillip editing its files.
- [ ] Confirm the selective surrogate always falls back when its gate defers.
- [ ] Confirm final selected candidates use the agreed full-model validation policy.
- [ ] Run `uv run pytest tests/test_contracts.py tests/test_pipeline.py`.
- [ ] Run `uv run ruff check .` and `uv run pytest` before pushing.
