# Sai TODO

Primary goal: make common Proto workflow topologies explicit, rankable, and reusable,
then prototype **ProtoStage**: an exact-first prepared-state layer that avoids repeated
work while preserving the scientific meaning of Phillip's original Proto workflow.

## Product hypothesis from the Proto Language benefits discussion

- [ ] Treat the central optimization artifact as a `PreparedModule`, not a cached final
  score: semantic signature, fixed inputs, residual graph, cached state, resume/update
  operations, validity rules, exactness, cost, and provenance hash.
- [ ] Keep the order of attack explicit: `prepare`, `prefill`, and `incremental` first;
  `factorize`, `reweight`, and `summarize` only behind validity/error contracts; learned
  `distill` last.
- [ ] Demonstrate one exact mode end to end before expanding scope. Select among target
  preparation, shared generator-prefix state, or mutation-delta recomputation using the
  measured reuse pattern in Phillip's workload.
- [ ] Treat proposed names such as `prepare` and `PreparedModule` as ProtoFuse design
  vocabulary until an approved adapter exists; do not assume they are current Proto APIs.

## Topology work

- [ ] Define reusable templates for propose-score-select, iterative refinement, staged
  filtering, multi-objective search, and closed-loop experiments.
- [ ] Describe required nodes, legal edges, iteration points, stopping policies, and
  selection policies for each template.
- [ ] Replace baseline scoring constants with named, testable features derived only
  from `MethodologySpec`.
- [ ] Add deterministic tie-breaking and an explanation for every recommendation.
- [ ] Score the effects of constraint count, explicit thresholds, optimizer stages,
  workflow loops, and experimental feedback separately.
- [ ] Add topology validation that rejects missing required nodes and invalid cycles.
- [ ] Benchmark recommendations against shared synthetic or redistributable fixtures.
- [ ] Preserve the public `recommend_topologies()` interface used by Phillip.

## ProtoStage graph analysis

- [ ] Consume Phillip's normalized `graph.json`, `workload.json`, and aggregate
  `profile.json`; do not infer the graph solely from Python source or Proto result
  exports.
- [ ] Verify the graph/profile bundle against `docs/GRAPH_HANDOFF.md` before ranking
  hot paths; request missing measurements rather than estimating them silently.
- [ ] Build a canonical typed DAG view whose nodes expose input/output roles,
  deterministic or stochastic behavior, side effects, context dependencies,
  batchability, cost, fidelity, cache semantics, version, and provenance.
- [ ] Perform binding-time analysis relative to the stated workload: classify every
  node as fixed-context, candidate-dependent, or mixed, and explain each classification.
- [ ] Rank opportunities by **amortized avoidable work**, not one-run duration alone:
  cost per call, reuse count, branch count, invalidation closure, cache footprint,
  transfer volume, and scientific-quality contribution.
- [ ] Generate a semantic signature from canonical graph structure, model/software
  versions, configuration, and fixed context so stale prepared state is invalidated.
- [ ] Produce a residual graph that contains only work still required for each candidate,
  branch, mutation, or stochastic extension.
- [ ] Define exact prepared-state modes where the dependency structure permits them:
  fixed target/context preparation, prefix-trie state sharing, and mutation-delta change
  propagation.
- [ ] Use conventional cache, batch, parallelize, fuse, reorder, and early-stop passes as
  measured baselines or complementary transforms, not as substitutes for dependency
  analysis.
- [ ] Protect generator/constraint semantics, joint outputs, selection thresholds,
  optimizer state, seed behavior, evidence level, and experimental side-effect
  boundaries. Wet-lab actions must never be silently replayed, duplicated, or reordered.
- [ ] For stochastic prepared state, define `replay`, `extend`, `branch`, `reweight`, and
  `refresh` separately; prevent sample reuse from being counted as new evidence.
- [ ] Require effective-sample-size or equivalent overlap evidence before reweighting a
  nearby ensemble; otherwise extend or refresh the original evaluator.
- [ ] Require an observable/error contract for factorized or summarized state, including
  which means, covariance, quantiles, joint samples, and named tail failures are and are
  not preserved.
- [ ] Never let approximate associations, summaries, factorization, or distillation hard
  prune a candidate without a separately validated certificate or rule.
- [ ] Return the Sai-to-Phillip bundle described in `docs/GRAPH_HANDOFF.md`:
  `summary.md`, `prepared_module_plan.json`, `graph_patch.json`,
  `benchmark_plan.json`, and `decision_record.md`.
- [ ] Estimate benefits and risks explicitly; label missing evidence as unknown rather
  than presenting an inferred speedup as measured.

## Intermediate check-ins and decisions

- [ ] **Check-in 0 — methodology:** Phillip and Sai approve the extracted
  `MethodologySpec`, evidence, assumptions, and unknowns before component binding.
- [ ] **Check-in 1 — graph and workload freeze:** Validate stable node IDs, typed edges,
  input roles, loops, side effects, reuse axes, and scientific invariants before
  accepting a profile.
- [ ] **Check-in 2 — baseline profile:** Confirm the candidate/target/prefix/mutation
  workload is representative, rank amortized avoidable work, and select exactly one
  ProtoStage demo mode.
- [ ] **Decision 1 — prepared-state proposal:** Present the binding-time split, state
  contract, exact-or-approximate declaration, invalidation rules, graph patch, predicted
  benefit, rollback path, and benchmark plan for Phillip's approval before code changes.
- [ ] **Decision 2 — benchmark gate:** Jointly accept, reject, or defer the proposal
  based on semantic equivalence or stated error bounds plus runtime, cost, memory, and
  scientific quality.
- [ ] **Check-in 3 — integration:** Verify the accepted graph survives Phillip's
  end-to-end execution and remains compatible with shared contracts before pushing.

## Integration checks

- [ ] Validate recommendations against `examples/toy_methodology.json` and keep
  multi-objective search ranked first for its two scored constraints.
- [ ] Confirm recommendation is deterministic for identical `MethodologySpec` inputs.
- [ ] Confirm ranking does not mutate the input specification.
- [ ] Confirm every recommendation has a score from 0 to 1 and at least one reason.
- [ ] Confirm feedback measurements make closed-loop topology eligible.
- [ ] Confirm specifications without an optimizer still receive a safe baseline
  topology.
- [ ] Confirm every proposed `graph_patch.json` operation targets a stable graph node
  and includes a protected-invariant check.
- [ ] Confirm hot-path rankings distinguish measured values from estimates and unknowns.
- [ ] Confirm benchmark comparisons use the same input fixture, seed, device class, and
  quality thresholds.
- [ ] Confirm an exact prepared module matches the unspecialized workflow output for the
  same inputs and seeds, including joint outputs and failure witnesses.
- [ ] Confirm a change to target, scaffold, model version, configuration, or other fixed
  context invalidates every dependent prepared-state entry.
- [ ] Confirm a candidate mutation recomputes the full dependency closure and nothing
  outside that closure when exact incremental execution is claimed.
- [ ] Confirm prefix reuse never crosses incompatible generator/model/configuration or
  constraint-automaton state.
- [ ] Confirm stochastic `extend` produces new samples, `replay` does not change sample
  counts, and no cache mode double-counts evidence.
- [ ] Confirm approximate prepared state reports its applicability domain, error and
  observable contract, and a fallback to the original full evaluator.
- [ ] Confirm experimental nodes are effectful barriers and cannot be cached or reordered
  as ordinary deterministic computations.
- [ ] Run `uv run pytest tests/test_selector.py`.
- [ ] Run the cross-owner suite: `uv run pytest tests/test_selector.py
  tests/test_pipeline.py`.
- [ ] Run `uv run protofuse recommend examples/toy_methodology.json` and inspect the
  serialized contract consumed by Phillip.
- [ ] Run the repository gates before pushing: `uv run ruff check .` and
  `uv run pytest`.

## Handoff completion

- [ ] Publish any scoring, topology, or graph-patch contract change before Phillip
  integrates it.
- [ ] Provide the expected recommendation, selected reuse mode, binding-time split,
  prepared-state signature, proposed graph change, protected invariants, and rollback
  trigger for each fixture.
- [ ] Verify Phillip's pipeline still compiles the recommendation into a safety-gated
  `ProtoPlan` and can execute or resume the optimized graph.
