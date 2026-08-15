# Phillip TODO

Primary goal: make the paper-to-Proto-plan path reliable end to end while consuming
shared contracts and Sai's topology recommendations through their public interfaces.

## Pipeline work

- [ ] Add a Paperclip or local-text ingestion adapter that records the paper identifier
  and source path without committing paper contents.
- [ ] Run ingestion through the shared `ScientificAgent` and persist a validated
  `MethodologySpec` under the ignored `data/specs/` directory.
- [ ] Preserve evidence for extracted claims and route missing methodology details to
  `unknowns`.
- [ ] Record extraction, topology-selection, binding, and execution failures as
  distinct pipeline stages.
- [ ] Pass the validated specification to `recommend_topologies()` without depending
  on Sai's ranking internals.
- [ ] Add a reviewed component registry and feed it to `compile_proto_plan()`.
- [ ] Keep plans non-executable while any generator, constraint, or optimizer binding
  is unresolved.
- [ ] Add the registry-backed Proto builder after parameter mappings are typed and
  validated.
- [ ] Save run metadata and outputs under the ignored `data/runs/` directory.

## Integration checks

- [ ] Validate the shared fixture: `uv run protofuse validate
  examples/toy_methodology.json`.
- [ ] Confirm the pipeline accepts Sai's highest-ranked `TopologyRecommendation`.
- [ ] Confirm an empty registry produces `executable=false` and lists every unresolved
  component.
- [ ] Confirm a complete reviewed registry produces `executable=true`.
- [ ] Confirm malformed workflow edges and incompatible contract fields fail before
  topology selection or Proto execution.
- [ ] Run `uv run pytest tests/test_contracts.py tests/test_pipeline.py`.
- [ ] Run the cross-owner suite: `uv run pytest tests/test_selector.py
  tests/test_pipeline.py`.
- [ ] Run the repository gates before pushing: `uv run ruff check .` and
  `uv run pytest`.

## Handoff to Sai

- [ ] Share one synthetic or redistributable `MethodologySpec` that exposes the next
  topology-selection friction point.
- [ ] Document the expected recommendation and why it matters to downstream execution.
- [ ] Re-run the end-to-end pipeline after Sai changes ranking or topology behavior.
