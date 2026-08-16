# Research slide charts

Slide-ready figures generated from aggregate ProtoFuse evaluation artifacts. Every figure is
exported as a high-resolution PNG for slides and an editable SVG for design work.

## Current figures

- `01-speedup-fidelity`: compares paired end-to-end speedup with top-10 selection fidelity for
  the three evaluated CUSTOM strategies.
- `02-routing-composition`: shows how selective routing uses the surrogate only on supported
  inputs and sends uncertain or out-of-distribution inputs to an exact path.
- `03-frozen-audit-gates`: shows the frozen held-out CUSTOM audit against its predeclared error,
  rank-correlation, and coverage thresholds.
- `04-slide-results`: renders `slide-results.csv` as a condensed evaluation summary table for the
  final slide in the evaluation deck.

## Regenerate

From the repository root:

```bash
uv run python charts/build_charts.py
```

The builder reads aggregate results under `data/analysis/` and writes a small
`source-data.json` beside the figures. That file records the exact values, source paths, and
SHA-256 hashes used in the charts without copying proposal traces, sequences, or model data.
The build fails when a required result is missing or violates an expected invariant.

## Suggested slide captions

1. **Speed with scientific fidelity.** On the 1,000-candidate eGFP/Lung workload, the adaptive
   policy preserves every top-10 set while delivering 9.72x net speedup. The faster sampled
   policy trades some selection fidelity for throughput. Exact parallelism preserves selection
   but uses eight CPU workers and avoids no scientific calculations.
2. **Acceleration is selective, not unconditional.** Supported CUSTOM proposals route through
   the surrogate, while unsupported Evo2 audit proposals are fully deferred to the exact path.
3. **The frozen CUSTOM audit passes every declared gate.** Accepted error is below its ceiling;
   rank correlation and selective coverage are above their floors on four untouched groups
   containing 4,000 proposals.

## Scope and caveats

- CUSTOM values are local CPU results for the released 239-aa eGFP/Lung workload. They do not
  establish speedup on other objectives, hardware, or sequence lengths.
- Sampled-window top-10 recall is a selection-fidelity endpoint; final validation cannot recover
  candidates already excluded by approximate pool-wide ranking.
- Exact-parallel speedup is a cores-for-time systems result, not a surrogate result.
- The Evo2 point demonstrates fail-closed routing on one independent scaled audit, not successful
  acceleration.

