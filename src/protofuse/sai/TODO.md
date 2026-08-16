# Sai TODO

Goal: learn reusable fusions from Phillip's frozen ordinary Proto programs so future user
programs automatically use them when compatible and safe.

## Pipeline timings

[`workspaces/phillip/PIPELINE_BENCHMARKS.md`](../../../workspaces/phillip/PIPELINE_BENCHMARKS.md)
· raw per-invocation JSON stays local under `workspaces/phillip/benchmark_runs/` (gitignored).

Phillip publishes **smoke-tier** wall times only — proof that bindings execute on Modal, not
performance data. Full-scale and paper-length timings are Sai's to produce; treat any full
numbers in the table below as stale spot checks, not a baseline.

Node-level profiles still go under `data/analysis/<collection_id>/` (gitignored).

## Active handoffs

This table contains collections whose manifest says `reviewed=true`, which is necessary but not
sufficient. Only `custom-egfp-lung`, `dnachisel-num1`, `evo2-enformer-borzoi`, and
`rfdiffusion3-af3-ppi` currently print `READY FOR HANDOFF`; do not launch another row until its
mechanical review passes. Program numbers are stable ordinals, not tier names. Two-program collections use
`design_001.py` for full and `design_002.py` for smoke, but the generated docstring is the
authority. Smoke is a reduced executable workload, not a fake program.

| Collection ID | Path | Primary program | Notes |
|---------------|------|-----------------|-------|
| `dnachisel-num1` | `proto_programs/generated/dnachisel-num1/` | **`design_001.py`** (936 bp) | Start with full for profiling; `design_002.py` is the reduced smoke tier. Historical full outer loop **138 s** — see benchmarks. |
| `esm2-protein-maturation` | `proto_programs/generated/esm2-protein-maturation/` | **`design_001.py`** (129 aa) | GPU MCMC; profile inside `run_esm2_protein_maturation(tier="full")`. |
| `antibody-cdr-maturation` | `proto_programs/generated/antibody-cdr-maturation/` | **`design_001.py`** (121 aa) | GPU CDR MCMC; best Sai fusion target after esm2. |
| `gpcr-cxcr4-miniprotein` | `proto_programs/generated/gpcr-cxcr4-miniprotein/` | **`design_001.py`** (70 aa) | RFdiffusion3+Boltz-2; `structure_binding` passes 4RWS hotspots. |
| `boltz2-state-sweep` | `proto_programs/generated/boltz2-state-sweep/` | **`design_001.py`** (491 aa XylE) | Boltz-2 sweep vs 4GBY/4GBZ; labelled RMSD ground truth for Sai fusion. |
| `freebindcraft-binder` | `proto_programs/generated/freebindcraft-binder/` | **`design_001.py`** (70 aa) | FreeBindCraft rejection sampling. |
| `symmetric-oligomer-ring` | `proto_programs/generated/symmetric-oligomer-ring/` | **`design_001.py`** (C6 pool) | Pool optimizer; protein scorer still DNA-heuristic. |
| `ppi-interface-specificity` | `proto_programs/generated/ppi-interface-specificity/` | **`design_001.py`** (65 aa) | Dual target/off-target; AF3 specificity is protein-DNA proxy. |
| `rfdiffusion3-boltz2-binder` | `proto_programs/generated/rfdiffusion3-boltz2-binder/` | **`design_001.py`** (70 aa) | RFdiffusion3 bootstrap + Boltz-2 cycling; shares 4RWS target. |
| `ligandmpnn-enzyme-redesign` | `proto_programs/generated/ligandmpnn-enzyme-redesign/` | **`design_001.py`** (3HTB) | LigandMPNN active-site MCMC on holo enzyme. |
| `bioemu-ensemble-filter` | `proto_programs/generated/bioemu-ensemble-filter/` | **`design_001.py`** (129 aa) | BioEmu ensemble RMSD vs 2LYZ; MCMC proxy for cycling. |
| `custom-egfp-lung` | `proto_programs/generated/custom-egfp-lung/` | **`design_001.py`** (717 bp, 1,000 candidates) | Approved exact reproduction; initial exact and sampled paired cohorts are complete. |
| `evo2-enformer-borzoi` | `proto_programs/generated/evo2-enformer-borzoi/` | **`design_001.py`–`design_003.py`** | Approved paper-scale regulatory patterns; H100/H200 OOM. Repo-owned Arc/NVIDIA 25.04 B200 service is implemented; deployment and a full-length call remain before tracing. |
| `rfdiffusion3-af3-ppi` | `proto_programs/generated/rfdiffusion3-af3-ppi/` | **`design_001.py`–`design_005.py`** | Approved, but AF3 is unavailable on Modal and the local host; not executable yet. |

Mechanical handoff gate: `uv run protofuse review <collection_id>` (checks hashes, source drift, PDB/hotspot binding, preflight). Paper-evidence failures on internal benchmark fixtures are expected until evidence quotes are added.

`evo2-enformer-borzoi` and `rfdiffusion3-af3-ppi` now pass their paper and handoff gates.
Only Evo2 `design_001.py`--`design_003.py` are result workloads; see
[`docs/EVO2_REPRODUCTION.md`](../../../docs/EVO2_REPRODUCTION.md) for deployment gates and order.
`af3-boltz2-state-sweep` remains unreviewed. The approved `custom-egfp-lung` primary program is
the exact 717-bp, 1,000-candidate workflow; use
[`docs/CUSTOM_REPRODUCTION.md`](../../../docs/CUSTOM_REPRODUCTION.md), and never substitute the
reduced-pool `design_002.py` diagnostic for results.

## Analyze program collections

- [x] Load and hash-check the `program_collection.py` handoff without importing it.
- [ ] **`dnachisel-num1` experiment:** collect and retain a full-tier campaign profile;
      the controlled import, tracing, and profiling code is already implemented.
- [x] Import reviewed `build_program()` entry points in a controlled analyzer.
- [x] Derive canonical signatures from model/tool identity and version, configuration,
      inputs, stochastic semantics, thresholds, weights, and optimizer position.
- [x] Record and profile observed call count, proposal count, parent latency, failures, and
      structure/logit outputs from append-only traces; unavailable accelerator, memory, and
      cost measurements remain `null`.
- [ ] Collect accelerator time, memory, cost, and decision-contribution measurements from
      real model campaigns.
- [ ] **Per-target experiment:** use real profiles to compare exact caching/shared
      intermediates with learned approximation. The runtime already batches surrogate and
      fallback calls and shares one routed multi-output evaluation across matched constraints.

## Train one learned fusion

- [ ] Jointly choose one expensive group and define all teacher inputs/outputs,
      applicability domain, thresholds, and asymmetric error costs.
- [x] Implement append-only joint full-model tracing and leakage-resistant group splits.
- [x] Implement a portable supervised multi-output ensemble baseline.
- [x] Calibrate ensemble disagreement, support distance, and held-out absolute-error bounds.
- [ ] Collect the real traces and approve the grouping and calibration thresholds for the
      first scientific target.
- [ ] Report selective risk versus coverage, false decisions, top-k recall, subgroup/OOD
      performance, full-model calls avoided, runtime, and cost.

## Automatic runtime

- [x] Register versioned fusion bundles with compatibility matchers.
- [x] Leave unmatched or failed program transformations unchanged.
- [x] Route per input through a surrogate gate with deterministic fail-closed fallback.
- [x] Implement a real Proto step-signature matcher and transactional transformation.
- [x] Implement paired full-versus-fused execution with identical seeds and route counts.
- [ ] Package the trained surrogate and gate as the first reviewed `FusionBundle`.
- [x] Preserve immediate final full-model validation; artifacts that request another policy
      are rejected.

Raw traces and calibration data stay under `data/analysis/`; weights stay under
`data/models/`.

All generic application code in this checklist is implemented. Remaining unchecked items
require real model runs, target-specific scientific choices, reporting, or human approval;
they are not placeholder functions waiting to be filled in.

## Future program collections (lower priority)

The retired CUSTOM smoke proxy and `dnachisel-num1` were weak fusion targets. The exact CUSTOM
v2 workflow has five ViennaRNA/CUSTOM objectives and must be profiled before its value is judged.
`gpcr-cxcr4-miniprotein` is the primary GPU-backed collection once Modal execution is
unblocked. When Phillip adds collections, prefer scenarios from
[`docs/CANDIDATE_WORKFLOWS.md`](../../../docs/CANDIDATE_WORKFLOWS.md) that repeat GPU
tools (ESMFold, Boltz-2, PARADE, AbLang) inside MCMC or pool loops.
