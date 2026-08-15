# Computation graph handoff

Sai needs a compact semantic graph and an aggregate runtime profile, not a Protocol
Buffers `.proto` file. In this project, "Proto" is the Python-based biological design
language. Its JSON export contains result tables and optimization history, but it does
not replace a normalized static graph with stable node IDs and node-level timing.

## Phillip to Sai

Place the reviewed, compact bundle in
`handoffs/phillip_to_sai/<decision_id>/`. Raw traces, program state, sequences, model
artifacts, and complete run exports stay under ignored `data/runs/<run_id>/`.

| File | Purpose |
| --- | --- |
| `summary.md` | Short scientific goal, workload, device, seed, and headline bottlenecks |
| `proto_plan.json` | Validated ProtoFuse plan and explicit approved bindings |
| `graph.json` | Typed static nodes, edges, dependencies, traits, stages, loops, invariants, and stable IDs |
| `workload.json` | Fixed/varying input roles, candidate/model/seed axes, shared prefixes, mutation relationships, branches, and expected reuse counts |
| `profile.json` | Aggregate per-node calls, duration, cost, memory, transfers, cache behavior, and quality contribution |
| `decision_request.md` | Target decision, allowed transformations, quality floor, budget, and deadline |

The static graph should include generators, constraints, optimizers, model/tool calls,
selection gates, experimental feedback, and material data transfers. Each node should
declare typed input/output roles; dependency keys; deterministic, stochastic, or
effectful behavior; version/configuration identity; cache semantics; fidelity; and
provenance when known. `workload.json` supplies the reuse scenario relative to which Sai
classifies nodes as fixed-context, candidate-dependent, or mixed. Metrics must carry
units and identify whether each value is measured, estimated, or unknown.

## Sai to Phillip

Place the response in `handoffs/sai_to_phillip/<decision_id>/`.

| File | Purpose |
| --- | --- |
| `summary.md` | Selected hot path and the recommended compression in plain language |
| `prepared_module_plan.json` | Binding-time split, semantic signature, cached state, residual graph, resume/update operations, exactness, invalidation rules, and fallback |
| `graph_patch.json` | Node/edge changes with expected benefit, semantic risk, and rollback operation |
| `benchmark_plan.json` | Controlled baseline/candidate inputs, seed, device, repetitions, metrics, and pass thresholds |
| `decision_record.md` | Proposed status followed by the joint accept/reject/defer decision |

The preferred first transformations are exact prepared-state operations: specialize
fixed target/context work, share causal generator-prefix state, or incrementally
recompute a mutation's dependency closure. Conventional caching, batching, parallelism,
fusion, ordering, and early stopping remain available. Factorization, stochastic
reweighting, summaries, reduced precision, and distillation are approximate unless
proved otherwise and require applicability, observable/error, invalidation, and fallback
contracts. No change is accepted solely because it is faster: the benchmark must also
preserve the agreed scientific invariants, selection thresholds, evidence semantics,
and reproducibility requirements.

For stochastic state, the plan must distinguish `replay`, `extend`, `branch`, `reweight`,
and `refresh`. For effectful nodes such as wet-lab experiments, the plan must prohibit
silent replay, duplication, or reordering.

## Decision sequence

1. Approve the extracted methodology.
2. Freeze the normalized graph, reuse workload, and scientific invariants.
3. Run a small representative baseline and choose one measured ProtoStage reuse mode.
4. Review Sai's prepared-module plan, graph patch, and benchmark plan before
   implementation.
5. Benchmark baseline and candidate under controlled conditions.
6. Record accept, reject, or defer, then perform Phillip's end-to-end integration run.

Compact, reviewed handoff files may be committed. Never commit raw paper text, raw run
traces, sequences, resumable state, credentials, model caches, or large generated
exports.
