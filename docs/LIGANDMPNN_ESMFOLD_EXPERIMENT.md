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
- Split: group-disjoint seeded trajectories; at least three development groups and four
  additional, hash-disjoint audit groups.
- Model comparison: linear ensemble, Extra Trees, and a small shared-hidden-layer MLP
  on the same frozen split. The portable runtime remains the linear ensemble unless
  another family is implemented and separately reviewed.
- Paired evaluation: counterbalanced Proto and ProtoFuse arm order, an excluded warmup
  pair, identical program seeds, and complete `Program.run()` timing.

“Joint” means one aligned two-output artifact, one inference call, and one routing
decision. The current linear baseline fits separate coefficient columns and does
not claim covariance-aware or nonlinear multi-task learning.

The fixed-length protein representation contains the 20 amino-acid 1-mer frequencies
plus a position-major 163-by-20 one-hot encoding. The earlier composition-only encoding
could not distinguish active-site positions and is retained only as rejected evidence.
The repeated native starting sequence is removed from every cleaned trajectory before
splitting so an exact baseline input cannot leak across development and held-out groups.

## Acceptance and failure policy

The frozen-artifact audit uses the repository defaults: accepted normalized MAE at
most `0.05` of each held-out objective's `q95-q05` range, accepted Spearman correlation
at least `0.90`, selective coverage at least `0.30`, and at least four held-out groups.

An unmatched, out-of-distribution, uncertain, invalid, or failed prediction must invoke
the complete LigandMPNN + ESMFold parent group. A run with no accepted surrogate routes
is a valid negative result, not a speedup. A timing claim is allowed only when both arms
finish, hardware policy matches, candidate generation is paired, and exact final
validation remains enabled.

Raw traces, model artifacts, structures, and run reports belong under ignored `data/`
paths and are not committed.

## Hackathon smoke result (2026-08-16)

Six development trajectories produced 30 aligned, non-baseline teacher samples. The
group-disjoint split contained 20 training, five calibration, and five development-audit
samples. Four later trajectories produced 20 baseline-free external audit samples with
no trace-hash, input-hash, or group overlap with development. All 150 retained cleaned
constraint rows were complete and error-free; the 180 raw rows remain preserved separately.

The same 3,280-column matrix was used to compare the linear ensemble, Extra Trees, and
small shared-hidden-layer MLP. None met the acceptance rule. The linear ensemble was kept
only as the portable exploratory baseline; the tree model did not improve ranking and the
MLP generalized poorly on the 30-sample cohort.

The frozen external audit correctly failed:

| Objective | Accepted MAE | MAE / held-out q95-q05 | Accepted Spearman |
| --- | ---: | ---: | ---: |
| LigandMPNN probability loss | 0.0718 | 0.2735 | 0.7010 |
| ESMFold confidence energy | 0.00440 | 0.2602 | 0.2843 |

Selective coverage was 17/20 (`0.85`), but the required normalized MAE is at most
`0.05` and required Spearman is at least `0.90` for every objective. The artifact
therefore remains `reviewed=false` and is not eligible for automatic deployment.

An explicitly exploratory, counterbalanced two-seed Modal H100 smoke comparison then
measured complete `Program.run()` calls, including fallback and mandatory final parent
validation:

| Result | Proto | ProtoFuse |
| --- | ---: | ---: |
| Total measured time | 47.64 s | 27.46 s |
| Final sequence agreement | 2/2 | 2/2 |
| Maximum final-energy difference | 0 | 0 |

Aggregate speedup was `1.73x`. ProtoFuse used seven surrogate routes and five full-parent
fallbacks across 12 routing decisions, then performed mandatory final validation. That
avoided ten net expensive target-model item evaluations, or eight net item evaluations
when the two extra cheap length validations are also charged to ProtoFuse. Per-seed speedups
were `1.27x` and `2.74x`; two smoke seeds are far too few for a stable timing claim. This is
useful proof that the joint LigandMPNN+ESMFold path executes and produced matching final
outcomes in these two runs, not evidence that the rejected surrogate is accurate enough
to approve.

The per-objective accuracy fields embedded in the paired report are frozen metrics from
the five-sample development audit; they are not shadow measurements from the timed runs.
The separate 20-sample external audit above is the approval authority.

Old no-variation proposals, infrastructure-stalled attempts, composition-only artifacts,
and pre-correction runtime-seed traces are preserved under rejected ignored-data paths.
The tracer now snapshots the pre-run constraint contract and records the program seed
separately, preventing Proto's derived child seeds from masquerading as contract drift.
This cohort predates trace schema `1.1`, so it also lacks the new seed-neutral full-program
source hash and cannot provide source-complete approval provenance. The pLDDT reporting-unit
correction changes metadata only; the continuous ESMFold score and every teacher target are
unchanged.
