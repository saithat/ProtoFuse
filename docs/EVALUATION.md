# ProtoFuse evaluation contract

This document defines the minimum evidence required before describing a program path as a
validated fusion. Missing measurements remain `null` or `not_run`; they must never be
coerced to zero.

## Current audit snapshot

As of 2026-08-15:

- Four Modal smoke workloads have full-model run summaries, but no paired learned-fusion
  run.
- One analysis-only CUSTOM pilot fits one ordinary least-squares matrix to two outputs:
  tissue codon score and GC fraction.
- That pilot has 1,198 training, 396 calibration, and 398 audit samples grouped by
  trajectory chain, plus a 1,998-sample full-trajectory holdout.
- Four hand-crafted OOD challenges are rejected. There are no held-out high-value positive
  cases or positive-but-uncertain cases for deferral testing.
- No learned surrogate is packaged as a reviewed `FusionBundle`.
- Twelve of 15 methodology fixtures point to a local source path (including the workflow
  rationale document used by several prototype fixtures). Across all fixtures, 32 of 62
  constraints have at least one evidence record. A source path or evidence record is not by
  itself proof that the encoding is a fair reading of the cited paper.

## Durable proposal trace

The execution layer writes a crash-safe operational checkpoint after every completed MCMC
step, cycling round, or rejection-sampling proposal batch. Separately, `protofuse trace`
instruments a reviewed program and appends proposal-level parent objective outputs, input and
program hashes, callable/config identity, latency, errors, and available structure/logit flags.
`protofuse fusion profile` aggregates calls once per batch so latency is not multiplied by the
proposal count. Raw campaign traces have not yet been collected for a reviewed fusion, and
accelerator time, memory, retries, cache status, and cost stay `null` until an execution backend
reports them.

Store one row per proposal under the ignored analysis data area. A row must contain:

- run, collection, program, methodology, code, and environment identifiers or hashes;
- paper identifier, objective implementation name, objective version, direction, units,
  thresholds, and normalization;
- tier, seed, chain, step, proposal, input hash, and parent-state hash;
- raw parent outputs and latency;
- raw surrogate outputs, uncertainty or conformity score, and latency;
- applicability-domain and gate thresholds;
- route, deferral reason, final decision, and whether the parent recovered the case;
- accelerator time, peak memory, retry count, cache status, and cost when available;
- final parent validation and any execution error.

The implemented trace writer is append-only, flushes each batch, and calls `fsync` before
returning. Store large/raw records and teacher traces outside Git as required by repository
policy. Commit only aggregate reports, schemas, and small test fixtures with no sensitive or
licensed content. Surrogate predictions and routes are currently reported by paired evaluation;
they must be joined into the durable campaign trace before the first artifact is approved.

## Split policy

Create versioned split manifests before training. Split by the strongest leakage unit
available: target, structure/scaffold, sequence family, or campaign. Never split adjacent
steps from the same trajectory across train and evaluation sets.

Required cohorts:

1. training;
2. calibration/validation;
3. in-domain test;
4. low-value or constraint-violating negative holdout;
5. high-value positive holdout that the surrogate should accept;
6. high-value but uncertain/OOD holdout that should defer to the parent;
7. unseen target/scaffold/family stress test;
8. temporal/drift holdout when trace collection spans model or data updates.

Report cohort definitions, counts, class balance, group counts, hashes, and seed. Deduplicate
before splitting.

## Paper-objective fidelity gate

Before a workload can be called paper-comparable:

1. Bind every evaluated objective to a paper quote or authoritative implementation.
2. Reproduce the paper's metric formula, direction, units, thresholds, preprocessing, and
   aggregation. Version this implementation.
3. Record unsupported substitutions in `unknowns`; do not fold them into a paper score.
4. Run a small golden set through both the reference implementation and ProtoFuse objective
   implementation and report their disagreement.
5. Report each objective separately. A local composite energy is additional context, not a
   substitute for the paper's objective.

If a paper has no executable or numerical reference target, label the result
`objective_matched` rather than `paper_reproduced`.

## Paired full-versus-fused protocol

Use the same inputs, split, seeds, stopping rule, objective implementation, and final parent
validation for both paths. Run enough independent seeds to report a distribution rather
than one wall time.

The executable harness is `protofuse fusion evaluate <artifact> <collection> <program-id>
--seed <seed> ...`. It records paired wall time, final-sequence agreement, final energy
difference, and route counts. The broader scientific measures below must be computed from
real campaign traces and reported before review; the presence of the harness does not mean
those runs have occurred.

For each pair, report:

- planned and completed steps, proposals, accepted moves, and parent calls;
- end-to-end wall time and per-step p50/p95 latency;
- accelerator time, memory, retries, failures, and cost;
- per-objective MAE/RMSE/max error, rank correlation, and threshold agreement;
- false acceptance of negative cases and false rejection of positive cases;
- selective risk versus coverage and deferral recovery;
- top-k recall, final objective regret, best-seen score curve, time-to-quality, and
  multi-objective Pareto hypervolume when relevant;
- full-model calls avoided and net speedup including routing/fallback overhead;
- seed-level win/tie/loss and confidence intervals.

Keep final full-model validation unless a separately reviewed policy explicitly removes it.
Any unmatched, uncertain, incompatible, OOD, or failed case must retain or invoke the
original full-model path.

## Visualization artifact contract

Raw execution data remains ignored. After a run, generate the tracked, reviewed visualization
bundle with `python3 scripts/build_visualization_bundle.py --strict`. The bundle contains only
final result sequences, attached final structures, explicitly labeled intermediate structures,
objective vectors, molecule records when available, stable identifiers, and source hashes.

Every candidate must say whether it is complete and whether it came from the full-model, fused,
or reference arm. Every structure must be labeled `final`, `intermediate`, or `reference` rather
than inferred from its filename. Molecules require canonical SMILES and should include an SDF path
when coordinates exist. Missing outputs stay in the bundle's `gaps` list so the report cannot
silently present an intermediate or prefix as a final design.
