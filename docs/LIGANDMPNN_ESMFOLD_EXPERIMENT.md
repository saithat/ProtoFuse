# LigandMPNN + ESMFold joint-surrogate experiment

## Question

Can ProtoFuse reduce repeated parent-model work while preserving an ordinary Proto
optimization that evaluates the same active-site sequence variants with two different
model families?

The experiment jointly optimizes two model-family objectives on every candidate:
LigandMPNN structure-conditioned sequence compatibility and ESMFold confidence.
A seeded local generator guarantees one non-identity active-site substitution per
step; proposal generation is not replaced by the surrogate. The enzyme sequence
remains fixed at the chain-A length registered from holo structure 3HTB, and only
the registered active-site positions may mutate.
Every proposal changes exactly one registered active-site residue.

## Parent objectives

The LigandMPNN objective is its existing probability loss, `1 - pMPNN`, in `[0, 1]`.
The ESMFold objective is `1 - normalized pLDDT`, also in `[0, 1]`. The LigandMPNN
energy has weight `1.0` and the ESMFold energy has weight `0.75`. Both are continuous
objectives that Proto minimizes on the same candidate sequence.

pLDDT `70` is a reporting target, not a hard optimization threshold. The ESMFold
adapter is score-only: it runs the ordinary ESMFold parent, preserves the exact scalar
pLDDT energy, and discards only the predicted structure and PDB text because no
downstream step consumes them. ProtoFuse's mandatory final validation still reruns
both original parent objectives on the selected output.

## Protocol

- Parent families: LigandMPNN and ESMFold.
- Proposal family: seeded uniform active-site mutation on 3HTB chain A; the current
  residue is excluded so every scored proposal differs from its parent.
- Fusion group: `mpnn_probability`, `structure_plddt` in optimizer `0`.
- Cheap constraint outside the group: `protein_length`.
- Development smoke: five MCMC steps with one guaranteed active-site substitution per step.
- Proto and ProtoFuse use the same program seeds and generator policy. Adaptive
  candidate-pool hashes are not currently exposed for this optimizer.
- Hardware: the same pinned Modal accelerator class, at most one container per parent
  service, zero retries, and the same warm-container policy for both paired arms.
- Split: 100 fresh development trajectories assigned as 60 training, 20 calibration,
  and 20 development-audit groups, followed by 20 separately collected external groups.
- Model selection: compact regularized linear models selected by inner group cross-validation.
  The development audit is model-selection evidence, not the confirmatory approval audit.
- Paired evaluation: counterbalanced Proto and ProtoFuse arm order, an excluded warmup
  pair, identical program seeds, and complete `Program.run()` timing.

“Joint” means one aligned two-output artifact, one inference call, and one routing
decision. The selected ridge ensemble fits separate coefficient columns and does
not claim covariance-aware or nonlinear multi-task learning.

The frozen representation contains one-hot categories only at the eight contract-declared
mutable positions: 62, 64, 91, 92, 94, 96, 119, and 121 in one-based protein numbering.
Twenty amino-acid categories at each position produce 160 features. This replaces the earlier
3,280-column whole-sequence representation and its composition-only predecessor. The repeated
native starting sequence is removed from every cleaned trajectory before splitting so an exact
baseline input cannot leak across development and held-out groups.

Post-audit hardening also binds compact artifacts to a hash of all 155 non-mutable scaffold
residues. A fixed-context mismatch raises during featurization and sends the whole objective group
to the parent models. Reviewed-artifact loading rejects selected-position models without that
binding. Campaign fitting now rebuilds every clean trace from raw data, rejects cross-group input
duplicates, derives mutable sites from the frozen generator configuration, and rechecks the three
artifact file hashes before every external collection or campaign audit.

## Acceptance and failure policy

The frozen-artifact audit uses the repository defaults: accepted normalized MAE at
most `0.05` of each held-out objective's `q95-q05` range, accepted Spearman correlation
at least `0.90`, selective coverage at least `0.30`, and at least 20 held-out groups.

An unmatched, out-of-distribution, uncertain, invalid, or failed prediction must invoke
the complete LigandMPNN + ESMFold parent group. A run with no accepted surrogate routes
is a valid negative result, not a speedup. A timing claim is allowed only when both arms
finish, hardware policy matches, candidate generation is paired, and exact final
validation remains enabled.

Raw traces, model artifacts, structures, and run reports belong under ignored `data/`
paths and are not committed.

## Larger v3 campaign result (2026-08-16)

Version 3 started from a fresh trace schema and frozen campaign protocol; no legacy teacher
trace was carried into training. The 100 development groups yielded 435 unique aligned samples
after removing 65 repeated inputs. Their deterministic group split contained 60 training groups
with 259 samples, 20 calibration groups with 87 samples, and 20 development-audit groups with
89 samples. Because those audit results informed the final representation and regularization,
the development audit is model-selection-only evidence.

The selected artifact is a compact 160-feature, two-output ridge ensemble with group-disjoint
inner cross-validation. It selected `alpha=1` without feature standardization for
`mpnn_probability`, and `alpha=10` with feature standardization for `structure_plddt`. The
100-group development cohort covered 146 of the 152 possible non-native residue-position
categories. The artifact and all training provenance were frozen before any external trace was
opened.

The subsequent external cohort contained 20 fresh groups and 70 unique samples after removing
30 repeated inputs. Trace hashes, group IDs, and input hashes had zero overlap with development;
all three disjointness and provenance checks passed. The frozen gate accepted 49 samples and
fell back to the complete parent group for 21, giving `0.70` selective coverage. Of the fallback
cases, 18 were out of domain and three had predictions outside the valid score range.

The confirmatory external audit failed:

| Objective | Accepted MAE / held-out q95-q05 | Required maximum | Accepted Spearman | Required minimum |
| --- | ---: | ---: | ---: | ---: |
| LigandMPNN probability loss | 0.08760199 | 0.05 | 0.932959 | 0.90 |
| ESMFold confidence energy | 0.09690646 | 0.05 | 0.814184 | 0.90 |

Coverage and LigandMPNN ranking passed their individual thresholds, but both normalized-MAE
checks and the ESMFold rank check failed. The artifact therefore remains `reviewed=false` and
all automatic routing remains ineligible. No paired full-versus-fused timing was run after this
failure, so v3 makes no speedup claim.

The byte-frozen artifact used for this audit predates the post-audit fixed-context field. Its
scores remain the recorded analysis result, but it is not a runtime candidate. A clean-room replay
from the same 100 development traces produced identical development metrics with the scaffold
binding and passed the strengthened freeze contract; it was not promoted or reselected using the
already-opened external labels.
