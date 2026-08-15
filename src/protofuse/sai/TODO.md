# Sai TODO

Goal: read Phillip's frozen Proto program folders, find recurring expensive step groups,
and build selective learned fusion that defers unreliable inputs to the original models.

## Analyze Phillip's programs

- [ ] Load `proto_programs/generated/<collection_id>/collection.json` and verify hashes.
- [ ] Import each inert `build_program()` without modifying the collection.
- [ ] Catalog model/tool steps, dependencies, configurations, inputs, outputs, thresholds,
      loops, and optimizer position.
- [ ] Profile call count, wall time, accelerator time, memory, failures, and cost.
- [ ] Rank recurring adjacent groups by total campaign cost and decision importance.
- [ ] Apply exact caching, batching, or shared intermediates before considering a learned
      approximation.

## Build one selective fusion experiment

- [ ] Jointly choose one expensive recurring group and define all teacher inputs/outputs,
      thresholds, applicability domain, and error costs.
- [ ] Collect joint full-model traces and split by target, scaffold, sequence family, or
      another leakage-resistant grouping.
- [ ] Train a supervised multi-output baseline before considering fine-tuning or RL.
- [ ] Estimate uncertainty with ensemble disagreement plus calibrated intervals or
      conformal scores.
- [ ] Defer OOD, unsupported, high-uncertainty, threshold-crossing, and failed calls to
      the complete original model group.
- [ ] Report selective risk versus coverage, false decisions, top-k recall, full-model
      calls avoided, runtime, and cost.

## Return one integration surface

- [ ] Expose one callable in `src/protofuse/sai/` for Phillip's final E2E run.
- [ ] Keep full-model fallback deterministic and fail closed.
- [ ] Preserve final full-model validation unless both explicitly change the policy.
- [ ] Keep raw data in `data/analysis/` and weights in `data/models/`.
