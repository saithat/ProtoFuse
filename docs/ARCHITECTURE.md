# Architecture

## Research flow

```text
Paper
  -> Phillip extracts MethodologySpec
  -> Phillip generates ordinary executable Proto programs
  -> proto_programs/generated/<collection_id>/
  -> Sai inspects many frozen programs and profiles recurring expensive step groups
  -> Sai trains and calibrates a reusable FusionBundle
  -> FusionBundle is registered with the ProtoFuse runtime
```

`proto_programs/generated/` is the only Phillip-to-Sai artifact interface. Sai derives
signatures, graph-like representations, profiles, and teacher data internally under
ignored `data/` paths.

## User runtime

The user does not write a fused program. They build an ordinary Proto program and call
`protofuse.optimize(program)`. The runtime walks the reviewed fusion registry in order:

1. A bundle performs a static compatibility match against the program's steps, versions,
   configuration, inputs, outputs, and semantics.
2. A compatible bundle transforms or wraps that step group.
3. At execution time, its `SelectiveRouter` evaluates the surrogate prediction and its
   calibrated applicability/uncertainty gate.
4. Accepted inputs use the surrogate. Rejected, OOD, unsupported, or failed inputs invoke
   the complete original model group.

If no bundle matches—or matching/transformation fails—the original program is returned.
The initial registry is empty, so current behavior is unchanged until a real reviewed
fusion is registered.

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
and routing fail closed, and the authoritative full-model path remains available.
