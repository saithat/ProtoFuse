# Architecture

## Research flow

```text
Paper
  -> Phillip extracts MethodologySpec
  -> Phillip generates ordinary executable Proto programs
  -> proto_programs/generated/<collection_id>/
  -> Sai inspects many frozen programs and profiles recurring expensive step groups
  -> Sai trains and calibrates a reusable FusionBundle
  -> a human reviews the scientific evidence and marks the artifact reviewed
  -> the ProtoFuse runtime discovers or receives the reviewed FusionBundle
```

`proto_programs/generated/` is the only Phillip-to-Sai artifact interface. Sai derives
signatures, graph-like representations, profiles, and teacher data internally under
ignored `data/` paths.

## User runtime

The user does not write a fused program. They build an ordinary Proto program and call
`protofuse.optimize(program)`. The runtime walks the reviewed fusion registry in order:

1. A bundle performs an exact static compatibility match against the program's optimizer
   position, component identity/version, configuration, inputs, outputs, thresholds,
   weights, and stochastic semantics.
2. A compatible bundle deep-copies the program and transactionally replaces only the
   matched score-only constraint group. A failed transformation leaves the input program
   untouched.
3. At execution time, the batch router evaluates the surrogate and applies its calibrated
   support-distance and ensemble-disagreement gates to each input independently.
4. Accepted inputs use the surrogate. Rejected, OOD, unsupported, or failed inputs invoke
   the complete original model group in a batched fallback call.
5. An immediate final constraint stage always runs the original matched objectives on the
   selected output; artifacts that request a weaker validation policy are rejected.

### Multi-output surrogate semantics

A fusion group preserves the selected Proto constraints as separate outputs. Training aligns
their teacher scores for the same proposal, one model call returns the score vector, and one gate
routes the complete group. Proto applies the original constraint weights after prediction; the
trainer does not collapse the vector into a scalar energy.

The current ordinary least-squares ensemble has one coefficient column per objective. Although
those columns live in one artifact and use the same features and bootstrap sample, the loss is
column-separable: it does not explicitly model output covariance or learn a shared nonlinear
representation. “Joint surrogate” in this repository therefore describes evaluation and routing,
not a statistical multi-task claim.

If no bundle matches—or matching/transformation fails—the original program is returned.
Callers may register a reviewed bundle programmatically. The default runtime also performs
one lazy discovery pass under `PROTOFUSE_BUNDLE_DIR`, or `data/models/` when the variable is
unset, and loads only hash-valid artifacts whose manifest says `reviewed=true`. The
repository currently contains no reviewed model artifact, so its checked-in default behavior
still leaves ordinary programs unchanged.

## Code boundaries

- `phillip/`: all paper conversion and program generation.
- `sai/`: analysis, fusion bundles, matching, learned models, gating, and routing.
- `program_collection.py`: shared folder schema and hash validation; it never imports the
  generated programs.
- `runtime.py`: thin public API delegating optimization to Sai's registry.

No Proto fork, graph-handoff directory, workflow dump, scenario catalog, or separately
generated fused-program folder is required.

## Safety

Paper text is untrusted. Generated programs use only reviewed symbols and typed
parameters; they never copy or execute paper-provided code, commands, URLs, or unreviewed
model identifiers. Program collections are hash-checked before analysis. Fusion matching
and routing fail closed, and the authoritative full-model path remains available. Training
always writes `reviewed=false`; implementing the pipeline never self-certifies a learned
artifact or substitutes for real traces, paired evaluation, and scientific approval.
