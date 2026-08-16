# BioEmu + ESMFold joint-surrogate experiment

## Question

Can ProtoFuse reduce repeated parent-model work while preserving an ordinary Proto
optimization that scores the same protein variants with two different model families?

The experiment jointly optimizes two model-family objectives on every candidate:
BioEmu ensemble similarity and ESMFold confidence. ESM-2 proposes sequence mutations,
but its output is not one of the two surrogate targets. The candidate protein remains
fixed at the registered benchmark length.

## Parent objectives

Each BioEmu result is converted to its existing sigmoid energy in `[0, 1]`; each
ESMFold result is `1 - normalized pLDDT` in `[0, 1]`. The BioEmu energy has weight
`1.0` and the ESMFold energy has weight `0.5`. Both are continuous objectives that
Proto minimizes on the same candidate sequence.

RMSD `4 Å` and pLDDT `70` are reporting targets, not hard optimization thresholds.
This is necessary for honest surrogate routing: the current runtime refuses to replace
hard threshold constraints. The reporting targets remain in parent metadata and results
can be stratified by whether they meet them.

The ESMFold adapter is score-only. It runs the ordinary ESMFold parent, preserves the
exact scalar pLDDT energy, and discards only the predicted structure and PDB text because
no downstream step consumes them. ProtoFuse's mandatory final validation still reruns
both original parent objectives on the selected output.

## Protocol

- Parent families: BioEmu and ESMFold.
- Proposal family: ESM-2 masked mutation.
- Fusion group: `ensemble_rmsd`, `structure_plddt` in optimizer `0`.
- Cheap constraint outside the group: `protein_length`.
- Development smoke: 80 residues, five MCMC steps, one BioEmu conformation per step.
- Result tier: increase samples only after the smoke proves every binding; never describe
  the reduced smoke as a paper reproduction.
- BioEmu parent seed: fixed at `0` so parent labels are repeatable across Proto and
  ProtoFuse arms. Program seeds vary ESM-2 proposals and are paired across arms.
- Hardware: the same pinned Modal accelerator class, one container, zero retries, and the
  same warm-container policy for both paired arms.
- Split: group-disjoint seeded trajectories; at least three development groups and four
  additional, hash-disjoint audit groups.
- Model comparison: linear ensemble, Extra Trees, and a small shared-hidden-layer MLP on
  the same split. The portable runtime remains the linear ensemble unless another family
  is implemented and separately reviewed.
- Paired evaluation: counterbalanced Proto and ProtoFuse arm order, an excluded warmup
  pair, identical program seeds, and complete `Program.run()` timing.

“Joint” means one aligned two-output artifact, one inference call, and one routing
decision. The checked-in linear baseline fits separate coefficient columns and does not
claim covariance-aware or nonlinear multi-task learning.

## Acceptance and failure policy

The frozen-artifact audit uses the repository defaults: accepted normalized MAE at most
`0.05` of each held-out objective's `q95-q05` range, accepted Spearman correlation at
least `0.90`, selective coverage at least `0.30`, and at least four held-out groups.

An unmatched, out-of-distribution, uncertain, invalid, or failed prediction must invoke
the complete BioEmu + ESMFold parent group. A run with no accepted surrogate routes is a
valid negative result, not a speedup. A timing claim is allowed only when both arms
finish, hardware policy matches, candidate generation is paired, and exact final
validation remains enabled.

Raw traces, model artifacts, structures, and run reports belong under ignored `data/`
paths and are not committed.
