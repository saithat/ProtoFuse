# Sai TODO

Primary goal: analyze collections of Proto designs, discover common expensive model-step
groups, and replace one group with a selective learned-fusion surrogate that defers
unsafe inputs to the original full models.

## Collection ingestion and step catalog

- [ ] Recursively scan `proto_programs/generated/<collection_id>/` for reviewed Python
  files listed in `collection.json`.
- [ ] Verify hashes, Proto/registry versions, entry points, input roles, and safety status
  before importing any generated program.
- [ ] Load each inert `build_program()` and catalog its optimizer stages, generators,
  constraints, model/tool calls, thresholds, loops, and data dependencies.
- [ ] Canonicalize a step by tool/model identity and version, configuration, input roles,
  fixed context, outputs, and stochastic seed semantics.
- [ ] Detect recurring step groups such as one structure model feeding several scorers or
  the same sequence/target being evaluated by Boltz plus another model.
- [ ] Preserve joint outputs, structures, failure witnesses, and provenance rather than
  reducing a group to disconnected scalar scores.

## Profiling and fusion-target selection

- [ ] Measure per-step and per-group wall time, cost, call count, batch size, device,
  memory, transfers, cache behavior, failures, and optimizer-decision contribution.
- [ ] Rank candidates using total measured cost, recurrence across designs, critical-path
  impact, and the fraction of calls a fused surrogate could avoid.
- [ ] Separate exact sharing opportunities from learned fusion: repeated identical
  preparation or model calls should be cached/shared before training a surrogate.
- [ ] Select exactly one common expensive group for the first experiment.
- [ ] Define its teacher inputs, joint outputs, scientific thresholds, downstream
  decisions, applicability domain, and asymmetric false-accept/false-reject costs.
- [ ] Record missing measurements as unknown instead of estimating silent speedups.

## Joint teacher dataset

- [ ] Store all outputs from the full step group for the same input as one versioned
  teacher trace, including model/configuration versions and stochastic seeds.
- [ ] Deduplicate exact evaluations without counting cached or replayed samples as new
  evidence.
- [ ] Partition by target, scaffold, sequence family, or experimental context—not only
  by random sequence—to measure transfer and out-of-domain behavior.
- [ ] Reserve independent train, validation, calibration, and final test groups.
- [ ] Retain rare failures and boundary cases; do not let common easy negatives dominate
  training.
- [ ] Track the monetary and compute budget for acquiring additional full-model labels.

## Selective learned-fusion surrogate

- [ ] Train a multi-task student with a shared representation and one typed head per
  decision-relevant teacher output.
- [ ] Start with supervised distillation or regression/classification losses; do not use
  RL until a supervised baseline and stable routing objective exist.
- [ ] Compare a simple baseline with a small ensemble of independently trained students.
- [ ] Estimate uncertainty using ensemble disagreement plus calibrated residual or
  prediction intervals; do not treat a raw confidence value as sufficient.
- [ ] Preserve joint decision behavior, including combinations of outputs used by the
  optimizer, rather than optimizing each output independently.
- [ ] Keep the original full step group as the authoritative fallback and final validator.

## Applicability and deferral gate

- [ ] Defer when an input is outside the training applicability domain.
- [ ] Defer when ensemble disagreement or calibrated interval width exceeds its limit.
- [ ] Defer when any interval crosses a selection threshold or top-k boundary.
- [ ] Defer when model heads disagree about the downstream decision, a required output is
  unsupported, or a named rare-failure rule requires full evaluation.
- [ ] Default new targets/scaffolds/families to full-model execution until separately
  calibrated evidence supports surrogate coverage.
- [ ] Return structured reason codes for every surrogate decision and every deferral.
- [ ] Send final selected candidates through the full model group unless both people
  explicitly approve a different validation rule.
- [ ] Feed deferred full-model traces back into an active-learning queue, but recalibrate
  on held-out data before changing the operating threshold.

## Calibration and benchmark

- [ ] Plot selective risk against coverage over all gate thresholds.
- [ ] Choose the operating point by a pre-agreed false-accept or false-reject risk limit,
  then maximize coverage within that limit.
- [ ] Report full-model calls avoided, wall-time and cost savings, false accepts, false
  rejects, top-k teacher recall, rank correlation, calibration error, and fallback rate.
- [ ] Break metrics down by target, scaffold, family, and in-domain versus out-of-domain
  inputs so aggregate performance cannot hide a weak subgroup.
- [ ] Compare full execution and selective fusion using identical programs, inputs,
  seeds, device class, repetitions, and final-validation policy.
- [ ] Treat standard conformal guarantees as calibration-distribution guarantees, not as
  proof of safety under arbitrary distribution shift.
- [ ] Reject the learned fusion if it cannot meet the agreed scientific risk at useful
  coverage or if its own inference cost erases the savings.

## Outputs and integration checks

- [ ] Write raw traces and training/calibration data under ignored `data/analysis/` and
  model weights under ignored `data/models/`.
- [ ] Produce the compact Sai-to-Phillip report in `docs/PROGRAM_COLLECTION.md`.
- [ ] Confirm collection scanning and profiling never modify Phillip's generated files.
- [ ] Confirm the same input and versions produce a deterministic routing decision,
  subject to the declared seed policy.
- [ ] Confirm every deferral invokes the complete original step group.
- [ ] Confirm cached/replayed teacher outputs are not counted as independent labels.
- [ ] Confirm final-validation and rare-failure policies cannot be bypassed by the
  surrogate.
- [ ] Run Sai's unit tests, a frozen synthetic collection, the cross-owner pipeline test,
  `uv run ruff check .`, and `uv run pytest` before pushing.
