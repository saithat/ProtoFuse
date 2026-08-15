# Sai TODO

Goal: learn reusable fusions from Phillip's frozen ordinary Proto programs so future user
programs automatically use them when compatible and safe.

## Active handoffs

| Collection ID | Path | Primary program | Notes |
|---------------|------|-----------------|-------|
| `dnachisel-num1` | `proto_programs/generated/dnachisel-num1/` | **`design_001.py`** (936 bp) | Skip `design_002.py` (100 bp smoke). Outer loop validated: `run_dnachisel_num1(tier="full")` ~113 s. |
| `custom-egfp-lung` | `proto_programs/generated/custom-egfp-lung/` | `design_001.py` (720 bp) | Outer loop: `run_custom_egfp_lung(tier="full")`. |

## Analyze program collections

- [x] Load and hash-check the `program_collection.py` handoff without importing it.
- [ ] **`dnachisel-num1`:** import and profile `design_001.py` inside `run_dnachisel_num1(tier="full")`.
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

## Future program collections (lower priority)

Current Phillip handoffs (`custom-egfp-lung`, `dnachisel-num1`) are CPU-only codon
workflows — weak fusion targets. When Phillip adds collections, prefer scenarios from
[`docs/CANDIDATE_WORKFLOWS.md`](../../../docs/CANDIDATE_WORKFLOWS.md) that repeat GPU
tools (ESMFold, Boltz-2, PARADE, AbLang) inside MCMC or pool loops.
