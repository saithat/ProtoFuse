# Architecture

## One folder handoff

```text
Paper
  -> Phillip's paper extractor
  -> MethodologySpec
  -> Phillip generates executable Proto programs
  -> proto_programs/generated/<collection_id>/
  -> Sai profiles recurring expensive step groups
  -> selective surrogate or full-model deferral
  -> Phillip runs the final workflow end to end
```

ProtoFuse remains one Python package and uses Proto Language as a pinned dependency. Sai
does not need a separate Proto fork unless a concrete instrumentation limitation later
proves that wrapping Proto's public objects is insufficient.

## Two engineering seams

1. **Phillip to Sai:** a frozen folder of readable, import-safe Python files. Each exposes
   `build_program()`. A small generated manifest lists the files and their hashes.
2. **Sai to Phillip:** one public callable in `src/protofuse/sai/` that wraps or transforms
   a built program with selective learned fusion and deterministic full-model fallback.

No separate graph-handoff directory, scenario registry, workflow dump, or benchmark
questionnaire is required. Sai can derive a graph-like representation and profiles from
the programs as internal analysis data.

## Safety

Paper text is untrusted. Generated programs may use only reviewed registry symbols and
typed parameters. They must not copy or execute paper-provided code, commands, URLs, or
unreviewed model identifiers. Raw inputs, traces, training data, and weights remain under
ignored `data/` paths.
