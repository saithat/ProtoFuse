# Phillip TODO

Primary goal: make the paper-to-Proto-plan path reliable end to end while consuming
shared contracts and Sai's topology recommendations through their public interfaces.

**How to execute:** Each item has a tag line (`wave`, `exec`, `spawn`, `tool`, `blocked`).
Read [`workspaces/phillip/AGENTS.md`](../../../workspaces/phillip/AGENTS.md) § TODO execution
before spawning subagents or running waves in parallel.

Philip–Sai artifacts:

- `philip-sai-integrations/` — versioned scenarios; [`v1/catalog.json`](../../../philip-sai-integrations/v1/catalog.json)
- `philip-sai-workflow-dump/` — handoffs (`phillip_to_sai/`, `sai_to_phillip/`)

---

## E2E tool map (built → planned)

| Phase | Check-in | Primary tools (today) | Output |
|-------|----------|----------------------|--------|
| A — Extract | 0 | `protofuse extract`, `run_pipeline()` | `data/specs/<paper>.json` |
| B — Plan | 0 | `protofuse validate`, `recommend`, `compile` | `ProtoPlan`, bindings |
| C — Handoff | 1 | `build_handoff_bundle()`, `write_handoff_bundle()` | `phillip_to_sai/<decision_id>/` |
| D — Benchmark | 2 | `protofuse benchmark baseline` | `data/runs/`, `profile_measured.json` |
| E — Sai review | 1 / Dec 1 | read-only | `sai_to_phillip/` |
| F — Compare | Decision 2 | `protofuse benchmark compare` | `benchmark_report.json` (deferred) |
| G — Integrate | 3 | full pipeline + gates | accepted E2E run |

Runbook for phase D: [`workspaces/phillip/BENCHMARK_PLAN.md`](../../../workspaces/phillip/BENCHMARK_PLAN.md).

---

## Phase A — Ingest and extract (Check-in 0)

- [ ] Add a Paperclip or local-text ingestion adapter that records the paper identifier
  and source path without committing paper contents.
  - `wave:A1` · `exec:parallel` · `spawn:explore` · `tool:—` · `blocked:none` · `src/protofuse/phillip/`

- [ ] Run ingestion through the shared `ScientificAgent` and persist a validated
  `MethodologySpec` under ignored `data/specs/`.
  - `wave:A2` · `exec:serial` · `spawn:shell` · `tool:protofuse extract <paper> --out data/specs/<id>.json` · `blocked:A1` · `data/specs/`

- [ ] Preserve evidence for extracted claims and route missing methodology details to
  `unknowns`.
  - `wave:A2` · `exec:serial` · `spawn:generalPurpose` · `tool:protofuse validate` · `blocked:A2-extract` · `contracts.py`

- [ ] Record extraction, topology-selection, binding, and execution failures as
  distinct pipeline stages.
  - `wave:A3` · `exec:parallel` · `spawn:generalPurpose` · `tool:—` · `blocked:check-in-0` · `src/protofuse/phillip/pipeline.py`

- [ ] **Gate — Check-in 0:** Phillip and Sai approve `MethodologySpec`, evidence,
  assumptions, and unknowns before component binding.
  - `wave:A-gate` · `exec:gate` · `spawn:none` · `tool:protofuse validate` · `blocked:human+sai` · `—`

---

## Phase B — Topology, registry, and Proto plan (Check-in 0 → 1)

- [ ] Pass the validated specification to `recommend_topologies()` without depending on
  Sai's ranking internals.
  - `wave:B1` · `exec:serial` · `spawn:shell` · `tool:protofuse recommend <spec>` · `blocked:check-in-0` · `run_pipeline()`

- [ ] Add a reviewed component registry and feed it to `compile_proto_plan()`.
  - `wave:B2` · `exec:parallel` · `spawn:explore` · `tool:protofuse compile` · `blocked:check-in-0` · `src/protofuse/integration/`

- [ ] Keep plans non-executable while any generator, constraint, or optimizer binding
  is unresolved.
  - `wave:B2` · `exec:parallel` · `spawn:generalPurpose` · `tool:protofuse compile` · `blocked:B2-registry` · `contracts.py`

- [ ] Add the registry-backed Proto builder after parameter mappings are typed and
  validated.
  - `wave:B3` · `exec:serial` · `spawn:generalPurpose` · `tool:—` · `blocked:B2-registry` · `src/protofuse/phillip/proto_builder.py`

---

## Phase C — Graph, workload, and handoff bundle (Check-in 1)

These can run **in parallel** after `ProtoPlan` exists (`wave:C*`).

- [ ] Emit normalized static `graph.json` from the reviewed `ProtoPlan` (stable node IDs
  for every generator, constraint, optimizer, gate, model call, transfer).
  - `wave:C1` · `exec:parallel` · `spawn:generalPurpose` · `tool:build_handoff_bundle()` · `blocked:phase-B` · `src/protofuse/phillip/handoff.py`

- [ ] Annotate graph nodes with typed I/O roles, dependency keys, traits, versions,
  batchability, cache semantics, fidelity, and provenance.
  - `wave:C1` · `exec:parallel` · `spawn:generalPurpose` · `tool:—` · `blocked:phase-B` · `handoff.py`

- [ ] Emit `workload.json` (reuse axes, no sensitive payloads).
  - `wave:C2` · `exec:parallel` · `spawn:generalPurpose` · `tool:build_handoff_bundle()` · `blocked:phase-B` · `handoff.py`

- [ ] Produce estimated `profile.json` for Sai ranking (before measured baseline).
  - `wave:C2` · `exec:parallel` · `spawn:generalPurpose` · `tool:—` · `blocked:phase-B` · `handoff.py`

- [ ] **Assemble handoff bundle** — `summary.md`, `proto_plan.json`, `graph.json`,
  `workload.json`, `profile.json`, `decision_request.md` per `docs/GRAPH_HANDOFF.md`.
  - `wave:C3` · `exec:serial` · `spawn:shell` · `tool:write_handoff_bundle()` · `blocked:C1+C2` · `philip-sai-workflow-dump/phillip_to_sai/`

- [ ] Keep bundle LLM-readable: stable IDs, units, no raw paper text or sequences.
  - `wave:C3` · `exec:serial` · `spawn:generalPurpose` · `tool:—` · `blocked:C3-assemble` · `phillip_to_sai/`

- [ ] Include `decision_request.md` (compression levers, invariants, budget, deadline).
  - `wave:C3` · `exec:serial` · `spawn:generalPurpose` · `tool:—` · `blocked:C3-assemble` · `phillip_to_sai/`

- [ ] Register scenario in catalog if new; link `handoff_decision_id` in manifest.
  - `wave:C4` · `exec:parallel` · `spawn:shell` · `tool:protofuse integrations validate` · `blocked:C3-assemble` · `philip-sai-integrations/`

- [ ] **Gate — Check-in 1:** Freeze graph and workload; both approve node IDs, edges,
  invariants before profiling.
  - `wave:C-gate` · `exec:gate` · `spawn:none` · `tool:integrations validate` · `blocked:human+sai` · `—`

---

## Phase D — Instrument, run, and benchmark (Check-in 2)

Runbook: [`BENCHMARK_PLAN.md`](../../../workspaces/phillip/BENCHMARK_PLAN.md).

- [ ] Instrument Proto runner: per-node calls, wall time, device, cache, memory,
  failures, quality change.
  - `wave:D1` · `exec:parallel` · `spawn:generalPurpose` · `tool:profile_program_run()` · `blocked:check-in-1` · `src/protofuse/phillip/profiler.py`

- [ ] Run Proto one stage at a time (`Program.run_stage()`, `get_stage_results()`).
  - `wave:D2` · `exec:parallel` · `spawn:explore` · `tool:—` · `blocked:check-in-1` · `proto_language`

- [ ] Save resumable state at stage boundaries (`Program.serialize_state()` → `data/runs/`).
  - `wave:D2` · `exec:parallel` · `spawn:generalPurpose` · `tool:—` · `blocked:check-in-1` · `data/runs/`

- [ ] Run measured baseline E2E (`dnachisel-v1`, seed 0, 3 reps).
  - `wave:D3` · `exec:serial` · `spawn:shell` · `tool:protofuse benchmark baseline --decision-id dnachisel-v1 --scenario dnachisel-gc-optimization --seed 0 --repetitions 3` · `blocked:check-in-1` · `BENCHMARK_PLAN.md`

- [ ] Write `profile_measured.json`; rank hot paths locally in `benchmark_summary.md`.
  - `wave:D3` · `exec:serial` · `spawn:shell` · `tool:benchmark baseline` · `blocked:D3-run` · `phillip_to_sai/dnachisel-v1/`

- [ ] Optional regression: Pipeline 1 `balanced-gc` smoke baseline.
  - `wave:D4` · `exec:parallel` · `spawn:shell` · `tool:protofuse benchmark baseline --decision-id balanced-gc-smoke --scenario balanced-gc` · `blocked:none` · `—`

- [ ] **Gate — Check-in 2 (solo):** Profile sufficient for hot-path ranking; **stop** before
  formal compare. Sai touch-base deferred.
  - `wave:D-gate` · `exec:gate` · `spawn:none` · `tool:—` · `blocked:human` · `BENCHMARK_PLAN.md`

---

## Phase E — Sai response (Phillip read-only)

- [ ] Read Sai's bundle under `sai_to_phillip/<decision_id>/` (`summary.md`,
  `prepared_module_plan.json`, `graph_patch.json`, `benchmark_plan.json`).
  - `wave:E1` · `exec:serial` · `spawn:none` · `tool:—` · `blocked:sai` · `sai_to_phillip/`

- [ ] **Gate — Decision 1:** Accept / reject / request changes on prepared-state proposal
  (semantic + execution risk). Phillip does **not** edit Sai's files.
  - `wave:E-gate` · `exec:gate` · `spawn:none` · `tool:—` · `blocked:human+sai` · `INTERFACE_CONTRACT_QUERY.md`

---

## Phase F — Decision 2 benchmark gate (deferred until touch-base)

- [ ] Run formal compare vs Sai's `benchmark_plan.json`.
  - `wave:F1` · `exec:serial` · `spawn:shell` · `tool:protofuse benchmark compare --decision-id dnachisel-v1` · `blocked:decision-1+sai` · `benchmark.py`

- [ ] Sai updates `decision_record.md` (accept / reject / defer).
  - `wave:F-gate` · `exec:gate` · `spawn:none` · `tool:—` · `blocked:sai` · `sai_to_phillip/`

---

## Phase G — Full integration (Check-in 3)

- [ ] Run accepted graph end to end; confirm reproducibility and contract compatibility.
  - `wave:G1` · `exec:serial` · `spawn:shell` · `tool:run_pipeline()` + `benchmark compare` · `blocked:decision-2` · `pipeline.py`

- [ ] Re-run E2E after Sai changes ranking, topology, or compression.
  - `wave:G2` · `exec:serial` · `spawn:shell` · `tool:full test suite` · `blocked:sai-change` · `—`

- [ ] **Gate — Check-in 3:** Both confirm before push.
  - `wave:G-gate` · `exec:gate` · `spawn:none` · `tool:ruff + pytest + integrations validate` · `blocked:human+sai` · `—`

---

## Verification waves (parallelizable after relevant phase)

Run together when their `blocked` phase is complete.

- [ ] Validate shared fixture: `uv run protofuse validate examples/toy_methodology.json`
  - `wave:V1` · `exec:parallel` · `spawn:shell` · `tool:protofuse validate` · `blocked:none`

- [ ] Pipeline accepts Sai's highest-ranked `TopologyRecommendation`
  - `wave:V1` · `exec:parallel` · `spawn:shell` · `tool:protofuse recommend` · `blocked:phase-B`

- [ ] Empty registry → `executable=false` with unresolved components listed
  - `wave:V2` · `exec:parallel` · `spawn:generalPurpose` · `tool:protofuse compile` · `blocked:phase-B`

- [ ] Complete registry → `executable=true`
  - `wave:V2` · `exec:parallel` · `spawn:generalPurpose` · `tool:protofuse compile` · `blocked:phase-B`

- [ ] Malformed edges / incompatible contracts fail before topology or Proto execution
  - `wave:V2` · `exec:parallel` · `spawn:generalPurpose` · `tool:pytest` · `blocked:phase-B`

- [ ] Every profiled node ID ∈ `graph.json`; every graph node observed or marked skipped
  - `wave:V3` · `exec:parallel` · `spawn:generalPurpose` · `tool:pytest` · `blocked:phase-D`

- [ ] `workload.json` deps refer to stable graph IDs; no raw sequences in handoff
  - `wave:V3` · `exec:parallel` · `spawn:generalPurpose` · `tool:pytest` · `blocked:phase-C`

- [ ] Stage checkpoints resume without changing baseline output (same seed)
  - `wave:V4` · `exec:parallel` · `spawn:generalPurpose` · `tool:pytest` · `blocked:phase-D`

- [ ] Compressed graph fails unless invariants and thresholds hold
  - `wave:V5` · `exec:parallel` · `spawn:generalPurpose` · `tool:pytest` · `blocked:decision-2`

- [ ] ProtoStage exactness: prepared vs unspecialized workflow (same inputs/seeds)
  - `wave:V5` · `exec:parallel` · `spawn:generalPurpose` · `tool:benchmark compare` · `blocked:decision-2`

- [ ] Invalidation / fallback on fixed-context, model-version, stochastic-state changes
  - `wave:V5` · `exec:parallel` · `spawn:explore` · `tool:—` · `blocked:decision-1`

- [ ] `uv run pytest tests/test_contracts.py tests/test_pipeline.py`
  - `wave:V-gate` · `exec:parallel` · `spawn:shell` · `tool:pytest` · `blocked:none`

- [ ] `uv run pytest tests/test_selector.py tests/test_pipeline.py`
  - `wave:V-gate` · `exec:parallel` · `spawn:shell` · `tool:pytest` · `blocked:none`

- [ ] Pre-push: `uv run ruff check .` && `uv run pytest` && `integrations validate`
  - `wave:V-gate` · `exec:serial` · `spawn:shell` · `tool:ruff + pytest + integrations validate` · `blocked:none`

---

## Handoff completion

- [ ] Share one synthetic / redistributable `MethodologySpec` + compact graph bundle.
  - `wave:H1` · `exec:parallel` · `spawn:generalPurpose` · `tool:—` · `blocked:check-in-3`

- [ ] Record chosen hot path, expected improvement, invariants, decision owner.
  - `wave:H1` · `exec:parallel` · `spawn:generalPurpose` · `tool:—` · `blocked:decision-2`

---

## Parallelization cheat sheet

| Wave | Can run together | Must wait for |
|------|------------------|---------------|
| `A1` | alone | — |
| `A2` | serial chain | `A1`, then `A-gate` |
| `B2` | `B2` items with each other | `check-in-0` |
| `C1` + `C2` | graph, workload, profile tasks | phase B, then `C3` serial |
| `C4` | catalog validate | `C3-assemble` |
| `D1` + `D2` | instrumentation + stage-run spikes | `check-in-1` |
| `D3` | serial baseline run | `D1`/`D2` or skip if profiler enough |
| `D4` | optional smoke | anytime |
| `V1`–`V2` | all verification in band | matching phase |
| `V-gate` | most pytest shards | before every push |

**Subagent spawn guide:** `explore` = find code/paths; `shell` = run CLI/tests; `generalPurpose` = implement or refactor in `src/protofuse/phillip/`. Never spawn into `sai_to_phillip/` or `src/protofuse/sai/`.
