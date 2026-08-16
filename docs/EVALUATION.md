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
- Only 3 of 12 methodology fixtures point to paper text. Across all fixtures, 21 of 51
  constraints have at least one evidence record.

## Durable proposal trace

The execution layer now writes a crash-safe operational checkpoint after every completed
MCMC step, cycling round, or rejection-sampling proposal batch. It also appends a summary row with
the completed-unit index, energy vector, and result-sequence hashes. This is sufficient to
resume paid model work and audit which units completed, but it is **not yet the eval-grade
teacher trace described below**: raw parent outputs, objective-level values, surrogate
predictions, routing decisions, and latency/cost fields are still missing.

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

The trace writer should be append-only and crash-tolerant. Store large/raw records and
teacher traces outside Git as required by repository policy. Commit only aggregate reports,
schemas, and small test fixtures with no sensitive or licensed content.

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
