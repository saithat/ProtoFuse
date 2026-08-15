# DNA Chisel NUM1 fixture

Internal methodology spec for Phillip's builder. **Not handed to Sai.**

Handoff target: generate `design_*.py` into
`proto_programs/generated/dnachisel-num1/`, finalize, commit. See
[`../../HANDOFF.md`](../../HANDOFF.md).

Parameters here drive `src/protofuse/phillip/program_builders.py`.

## Construct length: paper vs executable fixture

| Scope | Length | Notes |
|-------|--------|-------|
| Paper (Figure 1) | **2808 bp** | NUM1 CDS + synthesis/assembly flanks |
| Executable fixture (full tier) | **936 bp** | NUM1 CDS only — gene-scale unit for region-local solver |

The fixture uses **936 bp** for benchmarking because it matches the core codon-optimization
problem while keeping region-local + inner refinement runs in the ~1–2 minute range locally.

**This is not a proto-language length limit.** Preflight at 2808 bp confirms proto handles
long segments; the original failure was **binding infeasibility** (empty MCMC start + hard
homopolymer/BsaI filters). See [`../../WORKLOAD_VALIDATION.md`](../../WORKLOAD_VALIDATION.md).

## Preflight

Before changing `segment_length_bp` or scaling region passes:

```bash
uv run protofuse preflight dnachisel-num1 --length 2808
uv run protofuse preflight dnachisel-num1 --length 936 --strict
```

The builder seeds a filter-safe random sequence (`sequence_init.py`) so MCMC starts from a
valid state instead of empty `result_sequences`.
