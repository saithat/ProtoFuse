# Sai TODO

Goal: learn reusable fusions from Phillip's frozen ordinary Proto programs so future user
programs automatically use them when compatible and safe.

## Analyze program collections

- [x] Load and hash-check the `program_collection.py` handoff without importing it.
- [ ] Import reviewed `build_program()` entry points in a controlled analyzer.
- [ ] Derive canonical signatures from model/tool identity and version, configuration,
      inputs, outputs, stochastic semantics, thresholds, and optimizer position.
- [ ] Profile call count, latency, accelerator time, memory, failures, cost, and decision
      contribution across many programs.
- [ ] Rank recurring adjacent groups and apply exact caching/batching/shared intermediates
      before learned approximation.

## Train one learned fusion

- [ ] Jointly choose one expensive group and define all teacher inputs/outputs,
      applicability domain, thresholds, and asymmetric error costs.
- [ ] Collect joint full-model traces and split by target, scaffold, sequence family, or
      another leakage-resistant grouping.
- [ ] Train a supervised multi-output baseline before considering fine-tuning or RL.
- [ ] Calibrate ensemble disagreement plus prediction intervals or conformal scores.
- [ ] Report selective risk versus coverage, false decisions, top-k recall, subgroup/OOD
      performance, full-model calls avoided, runtime, and cost.

## Automatic runtime

- [x] Register versioned fusion bundles with compatibility matchers.
- [x] Leave unmatched or failed program transformations unchanged.
- [x] Route per input through a surrogate gate with deterministic fail-closed fallback.
- [ ] Implement a real Proto step-signature matcher and transformation.
- [ ] Package the trained surrogate and gate as the first reviewed `FusionBundle`.
- [ ] Preserve final full-model validation unless both explicitly change the policy.

Raw traces and calibration data stay under `data/analysis/`; weights stay under
`data/models/`.
