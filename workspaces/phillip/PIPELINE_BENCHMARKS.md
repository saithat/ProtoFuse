# Pipeline benchmarks (all Phillip workloads)

**Recorded:** 2026-08-16T05:42:13.145789+00:00
**Proto commit:** `041a70d06fd2d7b6eddb1059c2971eb0ec805603`
**Host:** PhilipThomasMac.local
**Modal profile:** configured

This is a timestamped run record, not the current feature matrix. A `skipped` row records
what this benchmark invocation omitted at capture time. In particular, the current CLI
supports `custom-egfp-lung` preflight even though this snapshot did not record it.

Re-run:

```bash
uv run python scripts/benchmark_pipelines.py --write-markdown
uv run python scripts/benchmark_pipelines.py --skip-modal-exec   # CPU only
uv run python scripts/benchmark_pipelines.py --rollup-only --write-markdown
```

Scope: **smoke tier only** — one `program.run()` per collection, enough to prove
bindings execute on GPU. Full-tier and paper-length timings are Sai's; absent
full-tier rows are expected, not a gap (`--full` opts in).

Rows are merged from per-invocation files in `benchmark_runs/` (newest wins per
pipeline/run/device), so concurrent sessions do not overwrite each other. This summary merges 1 run file(s); raw runs are gitignored.

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
| `dnachisel-num1` | `preflight_2808` | local | ok | 7.0 s | Paper construct length binding ladder |
| `dnachisel-num1` | `preflight_936` | local | ok | 0.7 s | Executable fixture length |
| `dnachisel-num1` | `outer_loop_smoke` | local | ok | 0.0 s | 100 bp, 1 region pass |
| `dnachisel-num1` | `compile_local` | local | ok | 0.0 s | Plan metadata only; MCMC executes locally regardless |
| `dnachisel-num1` | `compile_modal` | modal | ok | 0.0 s | Plan metadata only; MCMC executes locally regardless |
| `custom-egfp-lung` | `outer_loop_smoke` | local | ok | 0.5 s | 720 bp, n_pool smoke defaults |
| `custom-egfp-lung` | `preflight` | local | skipped | — | Not recorded in this snapshot; current CLI supports this preflight |
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
| `antibody-cdr-maturation` | `execute_smoke` | modal | failed | 1.3 s | ESM-2 + AbLang + ESMFold on Modal (smoke: CDR1, 30 steps) — TypeError: Constraint.__init__() got an unexpected keyword argument 'input_labels' |
| `bioemu-ensemble-filter` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `bioemu-ensemble-filter` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `bioemu-ensemble-filter` | `execute_smoke` | modal | failed | 600.0 s | BioEmu ensemble RMSD + ESM-2 on Modal (smoke: 20 steps, 2 samples) — killed after 600s with no result |
| `bioemu-ensemble-filter` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `bioemu-ensemble-filter` | `preflight_smoke` | local | ok | 0.1 s | 80 aa lysozyme smoke segment; build-only L0 |
| `freebindcraft-binder` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `freebindcraft-binder` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `freebindcraft-binder` | `execute_smoke` | modal | failed | 600.0 s | FreeBindCraft + AF2 validation on Modal (smoke: 5 samples) — killed after 600s with no result |
| `freebindcraft-binder` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `freebindcraft-binder` | `preflight_smoke` | local | ok | 0.3 s | 50 aa smoke binder; build-only L0 |
| `gpcr-cxcr4-miniprotein` | `compile_local` | local | ok | 0.0 s | Full tier requires Modal GPU tools at program.run() time |
| `gpcr-cxcr4-miniprotein` | `compile_modal` | modal | ok | 0.0 s | Full tier requires Modal GPU tools at program.run() time |
| `gpcr-cxcr4-miniprotein` | `execute_smoke` | modal | failed | 25.7 s | RFdiffusion3 + ProteinMPNN + Boltz-2 on Modal — IndexError: list index out of range |
| `gpcr-cxcr4-miniprotein` | `handoff_pipeline` | local | ok | 12.8 s | Paper ingest → compile (device=modal on plan) → generate → finalize |
| `ligandmpnn-enzyme-redesign` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `ligandmpnn-enzyme-redesign` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `ligandmpnn-enzyme-redesign` | `execute_smoke` | modal | ok | 317.5 s | LigandMPNN active-site MCMC on Modal (smoke: 20 steps) |
| `ligandmpnn-enzyme-redesign` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `ligandmpnn-enzyme-redesign` | `preflight_smoke` | local | ok | 0.1 s | 3HTB holo enzyme; build-only L0 |
| `ppi-interface-specificity` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `ppi-interface-specificity` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `ppi-interface-specificity` | `execute_smoke` | modal | failed | 12.3 s | Dual target/off-target scoring on Modal (smoke: 20 MCMC steps) —   See notes/storage.md for PROTO_MODEL_CACHE / PROTO_HOME rules. |
| `ppi-interface-specificity` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `ppi-interface-specificity` | `preflight_smoke` | local | ok | 0.2 s | 65 aa binder seed; build-only L0 |
| `rfdiffusion3-boltz2-binder` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `rfdiffusion3-boltz2-binder` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `rfdiffusion3-boltz2-binder` | `execute_smoke` | modal | failed | 47.9 s | RFdiffusion3 bootstrap + Boltz-2 cycling on Modal (smoke: 2 cycles) — IndexError: list index out of range |
| `rfdiffusion3-boltz2-binder` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `rfdiffusion3-boltz2-binder` | `preflight_smoke` | local | ok | 0.1 s | 50 aa smoke binder; build-only L0 |
| `symmetric-oligomer-ring` | `compile_local` | local | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `symmetric-oligomer-ring` | `compile_modal` | modal | ok | 0.0 s | GPU constraints require Modal at program.run() time |
| `symmetric-oligomer-ring` | `execute_smoke` | modal | failed | 28.7 s | Symmetry + ESMFold composite on Modal (smoke: pool=100) — ValueError: structure-radius-gyration requires structure_tool='alphafold2_binder'. |
| `symmetric-oligomer-ring` | `handoff_pipeline` | local | ok | 0.0 s | compile → generate → finalize via run_handoff_pipeline |
| `symmetric-oligomer-ring` | `preflight_smoke` | local | ok | 0.0 s | 60 aa C3 monomer smoke; build-only L0 |

## Primary programs for Sai

The filenames below are ordinal IDs. This snapshot's two-program collections map `001` to
full and `002` to smoke, but that is a collection convention rather than a global naming
rule; use each generated module's docstring as the authority.

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
