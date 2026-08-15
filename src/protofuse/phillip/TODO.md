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
- [ ] Emit a normalized static `graph.json` from the reviewed `ProtoPlan` before
  execution. Give every generator, constraint, optimizer stage, selection gate, model
  call, and data transfer a stable node ID.
- [ ] Annotate graph nodes with typed input/output roles, dependency keys,
  deterministic/stochastic/effectful traits, model and configuration versions,
  batchability, cache semantics, fidelity, and provenance so Sai can perform safe
  binding-time and invalidation analysis.
- [ ] Instrument the Proto runner to collect call count, wall time, device, cache hit,
  input/output shape, memory when available, failure count, and quality/energy change
  for each stable node ID.
- [ ] Emit `workload.json` describing reusable axes without sensitive payloads: fixed
  targets/contexts, candidate counts, shared prefix relationships, mutation deltas,
  model/seed axes, branch counts, and expected repeated invocations.
- [ ] Run Proto one stage at a time with `Program.run_stage()` so intermediate results
  can be inspected with `get_stage_results()` before the next stage is authorized.
- [ ] Save resumable state with `Program.serialize_state()` at accepted stage
  boundaries; keep state and raw outputs under the ignored `data/runs/` directory.
- [ ] Use `Program.export(format="json", include_proposals=True)` as a supplemental
  results artifact, not as a substitute for the static graph or node-level profile.

## Graph handoff to Sai

- [ ] Produce the Phillip-to-Sai bundle described in `docs/GRAPH_HANDOFF.md`:
  `summary.md`, `proto_plan.json`, `graph.json`, `workload.json`, `profile.json`,
  and `decision_request.md`.
- [ ] Keep the bundle easy for an LLM to read: stable IDs, short descriptions,
  explicit edges, aggregate metrics, units on every measurement, and no raw paper text,
  sequences, credentials, model weights, or executable instructions copied from a
  paper.
- [ ] Rank suspected hot paths by total wall time and cost, while also exposing reuse
  count, fixed-versus-varying inputs, invalidation scope, call count, memory, transfer
  volume, cache misses, fan-out, and quality contribution so Sai can estimate amortized
  avoidable work.
- [ ] Put raw traces in ignored `data/runs/<run_id>/`; commit only a compact, reviewed,
  non-sensitive handoff summary under `handoffs/phillip_to_sai/<decision_id>/`.
- [ ] Include a decision request naming the allowed compression levers, semantic
  invariants, quality thresholds, compute budget, and deadline.

## Intermediate check-ins and decisions

- [ ] **Check-in 0 — methodology:** Phillip and Sai approve the extracted
  `MethodologySpec`, evidence, assumptions, and unknowns before component binding.
- [ ] **Check-in 1 — graph and workload freeze:** Phillip presents the normalized graph
  and reuse workload; both approve node IDs, typed edges, input roles, loop/effect
  boundaries, and scientific invariants before profiling.
- [ ] **Check-in 2 — baseline profile:** Phillip runs a small representative baseline;
  Sai confirms the profile is sufficient to identify hot paths and selects the first
  optimization target.
- [ ] **Decision 1 — prepared-state proposal:** Sai returns the binding-time split,
  prepared-state/invalidation contract, graph patch, and benchmark plan; Phillip accepts,
  rejects, or requests changes based on semantic and execution risk before implementation.
- [ ] **Decision 2 — benchmark gate:** Both compare baseline and optimized runtime,
  cost, memory, and scientific-quality metrics and record accept/reject/defer.
- [ ] **Check-in 3 — integration:** Phillip runs the accepted graph end to end and both
  confirm reproducibility and contract compatibility before pushing.

## Integration checks

- [ ] Validate the shared fixture: `uv run protofuse validate
  examples/toy_methodology.json`.
- [ ] Confirm the pipeline accepts Sai's highest-ranked `TopologyRecommendation`.
- [ ] Confirm an empty registry produces `executable=false` and lists every unresolved
  component.
- [ ] Confirm a complete reviewed registry produces `executable=true`.
- [ ] Confirm malformed workflow edges and incompatible contract fields fail before
  topology selection or Proto execution.
- [ ] Confirm every profiled node ID exists in `graph.json` and every graph node is
  either observed, explicitly skipped, or marked unavailable in `profile.json`.
- [ ] Confirm every dependency and reuse claim in `workload.json` refers to stable graph
  IDs and uses symbolic identifiers or hashes rather than raw sequences or paper text.
- [ ] Confirm all accepted stage checkpoints can resume without changing the baseline
  output for the same seed.
- [ ] Confirm a compressed graph cannot pass unless the agreed scientific invariants
  and selection thresholds remain satisfied.
- [ ] Confirm a ProtoStage exactness claim by comparing prepared/resumed execution with
  the original unspecialized workflow for the same inputs and seeds.
- [ ] Confirm all fixed-context, model-version, configuration, and stochastic-state
  changes trigger Sai's declared invalidation or fallback behavior.
- [ ] Run `uv run pytest tests/test_contracts.py tests/test_pipeline.py`.
- [ ] Run the cross-owner suite: `uv run pytest tests/test_selector.py
  tests/test_pipeline.py`.
- [ ] Run the repository gates before pushing: `uv run ruff check .` and
  `uv run pytest`.

## Handoff completion

- [ ] Share one synthetic or redistributable `MethodologySpec` plus its compact graph
  handoff bundle.
- [ ] Record the chosen hot path, expected improvement, protected invariants, and
  decision owner.
- [ ] Re-run the end-to-end pipeline after Sai changes ranking, topology, or graph
  compression behavior.
