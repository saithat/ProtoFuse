# ProtoFuse evaluation contract

This document defines the minimum evidence required before describing a program path as a
validated fusion. Missing measurements remain `null` or `not_run`; they must never be
coerced to zero.

## Current audit snapshot

The CUSTOM numbers in this snapshot came from the retired 720-bp/two-objective smoke proxy.
They remain as negative historical evidence and must not be presented as the current reproduction.
The exact 717-bp/five-metric full-pool protocol, thresholds, paper comparison, and run order are in
[`CUSTOM_REPRODUCTION.md`](CUSTOM_REPRODUCTION.md).

As of 2026-08-15:

- Four Modal smoke workloads have full-model run summaries but no paired learned-fusion run.
  One local CUSTOM smoke fusion now has a paired diagnostic described below.
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

## Historical diagnostic: retired CUSTOM smoke proxy

On 2026-08-15, the executable comparison was run on the reviewed `custom-egfp-lung`
`design-002` smoke program. This is a local research diagnostic, not a full-tier result or a
paper comparison.

- Ten trajectories used explicit seeds 0–9 and distinct trajectory group IDs.
- The append-only trace contains 600 error-free constraint rows: 200 complete proposal samples
  for each of `tissue_codon_lung`, `gc_target`, and the unfused `homopolymer` filter. There are
  198 unique input hashes.
- The two scoring objectives used one deterministic 120/40/40 group split for
  train/calibration/audit. The raw trace SHA-256 is
  `21aa00737fbe222d9a705d887d0669956e7b7e87efc597da1c8ecca810e2d26a`.
- `gc_target` has only three distinct scores across the 200 proposals and is almost always zero,
  so its audit rank correlation is undefined. This cohort cannot select a model for GC behavior.

On the joint two-output audit, linear had tissue MAE `0.000878` and rank correlation `0.997`;
Extra Trees had tissue MAE `0.010603` and rank correlation `-0.099`; the small MLP had tissue MAE
`0.246112` and rank correlation `0.827`. Trees reproduced the nearly constant GC score best, but
that does not outweigh their loss of tissue ranking or repair the degenerate GC cohort. No joint
winner was declared.

A tissue-only diagnostic confirmed the capacity result: linear MAE `0.000878`, max error
`0.001273`, rank correlation `0.997`, and 45% selective coverage. Extra Trees had MAE `0.010909`
and rank correlation `0.120`; the MLP had MAE `0.156333` and rank correlation `-0.815`. The linear
artifact was packaged locally with `reviewed=false` solely for the required downstream paired
test.

Ten unseen paired seeds 10–19 then produced:

- 10/10 valid runs, identical final sequences, zero final-energy error, and no non-finite result;
- 70/200 surrogate routes (35% coverage), 93 uncertainty deferrals, and 37 OOD deferrals;
- full total `0.4111 s`, fused total `0.4074 s`, and net speedup `1.009x`;
- median seed speedup `0.904x` with bootstrap 95% interval `[0.893, 1.139]`.

The smoke fusion therefore fails the speedup claim despite preserving final accuracy. The parent
tissue scorer is already cheap, surrogate overhead is material, and conservative coverage is low.
Do not review or promote this artifact. The next useful paired experiment must target an actually
expensive parent objective and must include a non-degenerate objective challenge cohort.

The ignored local aggregate reports are `model-comparison.json` (SHA-256
`2ecdfe62ea71ec7bbe608f83c5182ea926f0cb160ed1fd161c823df5b2bb5095`),
`model-comparison-tissue-only.json` (SHA-256
`ef2da04cc6fb9ddd03d0efef520c0c635c09a9b4406d63326030202a7203f881`), and
`paired-tissue-linear.json` (SHA-256
`eaeb2cea03f1aa50ab9f8d58b44f97bb013b053e22b0561d01487041310f167a`).

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

Operational runs also write `events.jsonl` beside their checkpoint manifest. It is a durable,
ordered live-inspection stream covering run, program, and stage lifecycle events; optimizer
progress and timing; checkpoint decisions; resume activity; energy scores; result hashes; and
redacted failures. It deliberately excludes raw sequences and credentials. This operational log
does not replace the proposal-level teacher trace or add backend measurements that the provider
does not report.

## Split policy

Create versioned split manifests before training. Split by the strongest leakage unit
available: target, structure/scaffold, sequence family, or campaign. Never split adjacent
steps from the same trajectory across train and evaluation sets.

When multiple seeded trajectories form those groups, pass each seed explicitly to
`protofuse trace --seed <seed>` and give that complete trajectory one stable group ID. Changing
only the group label while replaying the same seed is duplicate data, not an independent group.

### From trajectories to model samples

A **trajectory** is one complete optimizer run from one starting program state with one explicit
seed. The optimizer's later proposals depend on its earlier proposals and accept/reject decisions,
so the proposal states within that run are correlated. A trajectory is therefore the minimum split
unit and the relevant independent sample for uncertainty statements.

Tracing writes one row for every evaluated constraint on every proposal. Training then aligns the
requested constraint rows for the same proposal into one vector-valued **teacher sample**. For
example, the current CUSTOM smoke collected ten 20-step trajectories:

```text
10 independent trajectory groups
  -> 20 aligned proposal states per trajectory
  -> 200 teacher samples per selected objective
  -> 600 raw rows when all three constraints are counted
```

The deterministic grouped split assigned six whole trajectories to training, two to calibration,
and two to audit. That produced 120/40/40 model samples, but the independent group counts remained
6/2/2. Randomly splitting the 200 proposal states would leak neighboring optimizer states across
cohorts and make accuracy look more certain than it is.

The current splitter hashes the stable group IDs with the declared split seed, then assigns about
60%/20%/20% of complete groups to train/calibration/audit. Report both the proposal-sample counts
and trajectory-group counts. The number of proposals per trajectory can differ by optimizer and
stopping rule, so sample counts must be measured rather than inferred from the nominal step count.

### Collection target for the next experiment

For the narrow, single-program hackathon claim, collect 100 independent teacher trajectories:

| Cohort | Trajectories | Approximate states at 20 proposals/run | Used for |
| --- | ---: | ---: | --- |
| Train | 60 | 1,200 | Fit each candidate model family and draw grouped learning curves |
| Calibration/validation | 20 | 400 | Choose family settings and calibrate support/uncertainty gates |
| Untouched test | 20 | 400 | One final surrogate accuracy, rank, and coverage report |

Keep another roughly 50 unseen trajectories for paired full-versus-fused runtime and downstream
accuracy, and construct 40--60 targeted challenge cases for OOD, constraint-boundary, non-finite,
and otherwise rare failures. Challenge cases are not a substitute for random test trajectories.

The 100-trajectory target is a starting design, not a universal guarantee. Plot grouped learning
curves at increasing training-group counts and gather more data when error, ranking, coverage, or
model-family ordering is still changing materially. For paired timing, inspect the confidence
interval sequentially and stop only when it clearly accepts or rejects the predeclared minimum
useful speedup.

The current `compare-models` command reports its internal audit cohort while model families are
being compared. Once that report is used to choose a family, the cohort is a development audit,
not an untouched confirmatory test. A new external test trace must remain unseen until the model,
features, and gate thresholds are frozen.

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

This experiment starts from an already built reviewed Proto program. Paper ingestion,
collection generation, artifact loading, and transformation are setup—not benchmark work.
The measured fused runtime includes surrogate prediction, gating, parent fallback, and final
parent validation because those costs are part of the claim.

Use the same inputs, split, seeds, stopping rule, objective implementation, and final parent
validation for both paths. Run enough independent seeds to report a distribution rather
than one wall time.

The executable harness is `protofuse fusion evaluate <artifact> <collection> <program-id>
--seed <seed> ... --out <report.json>`. By default it runs one unmeasured warmup pair, then
counterbalances full-first and fused-first measured runs. The warmup durations are reported
but never enter the primary speedup. A whole warmup run is not a pure cold-start measurement,
so the harness does not subtract it from measured runs or label it as cold-start time.

Proto requires evaluated scoring constraints to return finite scores in `[0, 1]` unless a
reviewed raw-score scorer is used. Internally, NaN means a proposal was not evaluated, while
`+inf` initializes rejected or unfilled optimizer results. The experiment records those
states categorically, converts their JSON energy value to `null`, and excludes them from
numeric error. A non-finite final energy makes that pair invalid for numeric accuracy even
when both arms have the same non-finite pattern.

Runtime and surrogate accuracy are separate measurements. Runtime runs never shadow-score
surrogate-accepted proposals with the parent because doing so would erase the speedup. The
artifact's held-out audit supplies per-objective error, rank quality, and selective coverage;
the paired run supplies warm runtime, final outcome quality, routing, and reliability.

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

## Surrogate model comparison

### What “joint” means

The current trainer joins all requested objective scores for the same proposal and emits one
vector-valued artifact. At runtime, one inference call predicts that vector and one conservative
gate accepts or defers the complete group. It does **not** train against Proto's weighted total
energy. Preserving separate outputs keeps objective-specific error, thresholds, weights, and
Pareto analysis visible.

The current linear least-squares matrix is still column-separable: fitting all output columns at
once gives the same coefficients as fitting one linear regression per objective. The objectives
share features, grouped bootstrap samples, support detection, and routing, but the model has no
explicit covariance term or shared nonlinear representation. Describe it as a **multi-output
linear surrogate**, not as a covariance-aware multi-task surrogate.

### Models to compare

There is no literature-supported universal winner. Use the exact same grouped split and compare
the smallest credible families:

| Family | Use here | Main limitation |
| --- | --- | --- |
| Linear ensemble | Required interpretable baseline for additive/composition objectives | Cannot express complex nonlinear interactions |
| Tree ensemble | Primary nonlinear comparator for small or medium tabular feature sets | Ensemble spread is only an empirical uncertainty estimate |
| Independent GP per objective | Optional small-data comparator after reducing feature dimension | Cubic scaling and awkward high-dimensional sequence inputs |
| Small shared-trunk, multi-head network | Comparator when traces or pretrained embeddings are sufficient | Easy to overfit and become confidently wrong OOD |

The executable first comparison deliberately implements only the three families that use the
current feature matrix without another representation pipeline:

```bash
uv run protofuse fusion compare-models \
  --trace data/analysis/<collection>/teacher.jsonl \
  --optimizer-index 0 --constraint <objective-a> --constraint <objective-b> \
  --seed 0 --out data/analysis/<collection>/model-comparison.json
```

It featurizes once, freezes one group-level train/calibration/audit split, and fits a bootstrap
ordinary-least-squares ensemble, Extra Trees, and an ensemble of one-hidden-layer multi-output
MLPs using the small-data L-BFGS solver. Each family uses the same support-distance rule and
calibrates its ensemble-disagreement threshold on the same calibration cohort. Inference latency
excludes one warmup prediction.

The report contains configuration, fit warnings/time, estimated serialized size, calibration and
audit MAE/RMSE/max error, rank correlation, support and uncertainty coverage, in-range fraction,
accepted-only error, a five-point selective-risk curve, and warm batch/item p50/p95 latency. It
sets `automatic_winner=null`; thresholds must be declared and reviewed before selection. The
command never writes a deployable model. A tree or MLP result can justify a later artifact-format
change, but cannot silently enter the runtime.

Report per-objective MAE/RMSE/max error, rank correlation, selective risk/coverage, inference
latency, and artifact size. Also report downstream paired optimization outcomes; predictive error
alone does not establish that a surrogate is safe under optimization. Choose the simplest family
that meets predeclared per-objective accuracy, coverage, and latency thresholds.

If all families fail on k-mer/composition inputs, improve the representation. A deeper model
cannot recover sequence order or structural information discarded by its features. For protein
workloads, a frozen pretrained sequence representation plus a small supervised head is a more
credible deep comparator than training a large network from scratch.

Do not make a scalarized-energy surrogate the default. ParEGO establishes scalarized surrogates as
a valid multi-objective strategy, while PESMO and related methods preserve one surrogate per
objective. Multi-output Gaussian processes can additionally model correlations, at greater
complexity. Treat these as empirical alternatives, not interchangeable meanings of “joint.”

### Literature anchors

- Jin, *Surrogate-assisted evolutionary computation: Recent advances and future challenges*
  (2011), especially the need for model management and continued real-fitness evaluation:
  <https://doi.org/10.1016/j.swevo.2011.05.001>.
- Jones, Schonlau, and Welch, *Efficient Global Optimization of Expensive Black-Box Functions*
  (1998), the Gaussian-process/EGO foundation: <https://doi.org/10.1023/A:1008306431147>.
- Knowles, *ParEGO: A Hybrid Algorithm With On-Line Landscape Approximation for Expensive
  Multiobjective Optimization Problems* (2006), a scalarized GP approach:
  <https://doi.org/10.1109/TEVC.2005.851274>.
- Hernández-Lobato et al., *Predictive Entropy Search for Multi-objective Bayesian Optimization*
  (2016), preserving objective-specific GP models: <https://proceedings.mlr.press/v48/hernandez-lobatoa16.html>.
- Hutter, Hoos, and Leyton-Brown, *Sequential Model-Based Optimization for General Algorithm
  Configuration* (2011), random-forest surrogates for structured spaces:
  <https://www.cs.ubc.ca/~hoos/Publ/HutEtAl11.pdf>.
- Snoek et al., *Scalable Bayesian Optimization Using Deep Neural Networks* (2015), a neural
  surrogate alternative when GP scaling is limiting: <https://proceedings.mlr.press/v37/snoek15.html>.
- Fannjiang and Listgarten, *Autofocused Oracles for Model-Based Design* (2020), the danger of
  optimizing a predictor outside its training distribution:
  <https://proceedings.neurips.cc/paper/2020/hash/972cda1e62b72640cb7ac702714a115f-Abstract.html>.
- Biswas et al., *Low-N Protein Engineering with Data-Efficient Deep Learning* (2021), pretrained
  protein representations with small labeled sets: <https://doi.org/10.1038/s41592-021-01100-y>.

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
