# Sai TODO

Primary goal: make common Proto workflow topologies explicit, rankable, and optimizable
without depending on the paper-extraction provider or Phillip's pipeline internals.

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

## Integration checks

- [ ] Validate recommendations against `examples/toy_methodology.json` and keep
  multi-objective search ranked first for its two scored constraints.
- [ ] Confirm recommendation is deterministic for identical `MethodologySpec` inputs.
- [ ] Confirm ranking does not mutate the input specification.
- [ ] Confirm every recommendation has a score from 0 to 1 and at least one reason.
- [ ] Confirm feedback measurements make closed-loop topology eligible.
- [ ] Confirm specifications without an optimizer still receive a safe baseline
  topology.
- [ ] Run `uv run pytest tests/test_selector.py`.
- [ ] Run the cross-owner suite: `uv run pytest tests/test_selector.py
  tests/test_pipeline.py`.
- [ ] Run `uv run protofuse recommend examples/toy_methodology.json` and inspect the
  serialized contract consumed by Phillip.
- [ ] Run the repository gates before pushing: `uv run ruff check .` and
  `uv run pytest`.

## Handoff to Phillip

- [ ] Publish any scoring or topology contract change before Phillip integrates it.
- [ ] Provide the expected top recommendation and explanation for each new fixture.
- [ ] Verify Phillip's pipeline still compiles the recommendation into a safety-gated
  `ProtoPlan`.
