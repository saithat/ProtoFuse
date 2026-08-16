# Pipeline benchmarks (all Phillip workloads)

**Recorded:** 2026-08-16T00:03:26.989657+00:00
**Proto commit:** `dec375b04fa26b1c809b248f1a6af2767da32293`
**Host:** mac
**Modal profile:** configured

Re-run:

```bash
uv run python scripts/benchmark_pipelines.py
uv run python scripts/benchmark_pipelines.py --skip-modal-exec   # CPU only
```

Machine-readable record: [`PIPELINE_BENCHMARKS.json`](PIPELINE_BENCHMARKS.json).

Per-pipeline handoff timing notes:

- [`TIMING_gpcr-cxcr4-miniprotein.json`](TIMING_gpcr-cxcr4-miniprotein.json)
- [`TIMING_esm2-protein-maturation.json`](TIMING_esm2-protein-maturation.json)
- [`TIMING_antibody-cdr-maturation.json`](TIMING_antibody-cdr-maturation.json)
- [`TIMING_freebindcraft-binder.json`](TIMING_freebindcraft-binder.json)
- [`TIMING_symmetric-oligomer-ring.json`](TIMING_symmetric-oligomer-ring.json)
- [`TIMING_ppi-interface-specificity.json`](TIMING_ppi-interface-specificity.json)

## Summary

| Pipeline | Run | Device | Status | Wall time | Notes |
| --- | --- | --- | --- | --- | --- |
| `dnachisel-num1` | `preflight_2808` | local | ok | 6.6 s | Paper construct length binding ladder |
| `dnachisel-num1` | `preflight_936` | local | ok | 0.6 s | Executable fixture length |
| `dnachisel-num1` | `outer_loop_smoke` | local | ok | 0.0 s | 100 bp, 1 region pass |
| `dnachisel-num1` | `compile_local` | local | ok | 0.0 s | Plan metadata only; MCMC executes locally regardless |
| `dnachisel-num1` | `compile_modal` | modal | ok | 0.0 s | Plan metadata only; MCMC executes locally regardless |
| `custom-egfp-lung` | `outer_loop_smoke` | local | ok | 0.5 s | 720 bp, n_pool smoke defaults |
| `custom-egfp-lung` | `preflight` | local | skipped | — | CLI preflight not implemented for this fixture |
| `custom-egfp-lung` | `compile_local` | local | ok | 0.0 s | Plan metadata only; pool loop executes locally regardless |
| `custom-egfp-lung` | `compile_modal` | modal | ok | 0.0 s | Plan metadata only; pool loop executes locally regardless |
| `esm2-protein-maturation` | `preflight_smoke` | local | ok | 0.0 s | 80 aa smoke segment; build-only L0 |
| `esm2-protein-maturation` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `esm2-protein-maturation` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `esm2-protein-maturation` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `esm2-protein-maturation` | `execute_smoke` | modal | skipped | — | --skip-modal-exec |
| `antibody-cdr-maturation` | `preflight_smoke` | local | ok | 0.0 s | 121 aa nanobody framework; build-only L0 |
| `antibody-cdr-maturation` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `antibody-cdr-maturation` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `antibody-cdr-maturation` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `antibody-cdr-maturation` | `execute_smoke` | modal | skipped | — | --skip-modal-exec |
| `freebindcraft-binder` | `preflight_smoke` | local | ok | 0.9 s | 50 aa smoke binder; build-only L0 |
| `freebindcraft-binder` | `handoff_pipeline` | local | ok | 0.1 s | compile → generate → finalize via run_handoff_pipeline |
| `freebindcraft-binder` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `freebindcraft-binder` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `freebindcraft-binder` | `execute_smoke` | modal | skipped | — | --skip-modal-exec |
| `symmetric-oligomer-ring` | `preflight_smoke` | local | ok | 0.0 s | 60 aa C3 monomer smoke; build-only L0 |
| `symmetric-oligomer-ring` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `symmetric-oligomer-ring` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `symmetric-oligomer-ring` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `symmetric-oligomer-ring` | `execute_smoke` | modal | skipped | — | --skip-modal-exec |
| `ppi-interface-specificity` | `preflight_smoke` | local | ok | 0.7 s | 65 aa binder seed; build-only L0 |
| `ppi-interface-specificity` | `handoff_pipeline` | local | ok | 0.1 s | compile → generate → finalize via run_handoff_pipeline |
| `ppi-interface-specificity` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `ppi-interface-specificity` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `ppi-interface-specificity` | `execute_smoke` | modal | skipped | — | --skip-modal-exec |
| `gpcr-cxcr4-miniprotein` | `handoff_pipeline` | local | ok | 16.6 s | Paper ingest → compile (device=modal on plan) → generate → finalize |
| `gpcr-cxcr4-miniprotein` | `compile_local` | local | ok | 0.0 s | Full tier requires Modal GPU tools at program.run() time |
| `gpcr-cxcr4-miniprotein` | `compile_modal` | modal | ok | 0.0 s | Full tier requires Modal GPU tools at program.run() time |
| `gpcr-cxcr4-miniprotein` | `execute_smoke` | modal | skipped | — | --skip-modal-exec |

## Primary programs for Sai

| Collection | Profile this | Skip |
| --- | --- | --- |
| `dnachisel-num1` | `design_001.py` (936 bp full outer loop) | `design_002.py` smoke |
| `custom-egfp-lung` | `design_001.py` (720 bp full pool) | `design_002.py` smoke |
| `esm2-protein-maturation` | `design_001.py` (129 aa lysozyme, 200 steps) | `design_002.py` smoke |
| `antibody-cdr-maturation` | `design_001.py` (121 aa, 3 CDR passes) | `design_002.py` smoke |
| `freebindcraft-binder` | `design_001.py` (70 aa, 50 samples) | `design_002.py` smoke |
| `symmetric-oligomer-ring` | `design_001.py` (C6, pool=1000) | `design_002.py` smoke |
| `ppi-interface-specificity` | `design_001.py` (100 steps, MPNN) | `design_002.py` smoke |
| `gpcr-cxcr4-miniprotein` | `design_001.py` (70 aa, 10 samples) | `design_002.py` unless debugging |

## Modal vs local

- **CPU codon workloads** (`dnachisel-num1`, `custom-egfp-lung`): execution is always local CPU. `--device modal` on `protofuse compile` only tags the plan.
- **GPU protein workloads** (`esm2-protein-maturation`, `antibody-cdr-maturation`, `gpcr-cxcr4-miniprotein`): `compile_proto_plan(..., device="modal")` matches runtime — `program.run()` invokes ESM-2/ESMFold, AbLang, RFdiffusion3, or Boltz-2 on Modal GPUs.

Detailed node profiles for Sai belong under `data/analysis/<collection_id>/` (gitignored). This file records orchestrator-level wall times only.
