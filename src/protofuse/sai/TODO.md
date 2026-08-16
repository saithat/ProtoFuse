# Sai TODO

Goal: learn reusable fusions from Phillip's frozen ordinary Proto programs so future user
programs automatically use them when compatible and safe.

## Pipeline timings

Orchestrator wall times (local execute + Modal compile/execute attempts):
[`workspaces/phillip/PIPELINE_BENCHMARKS.md`](../../../workspaces/phillip/PIPELINE_BENCHMARKS.md)
· JSON: [`PIPELINE_BENCHMARKS.json`](../../../workspaces/phillip/PIPELINE_BENCHMARKS.json).

Node-level profiles still go under `data/analysis/<collection_id>/` (gitignored).

## Active handoffs

| Collection ID | Path | Primary program | Notes |
|---------------|------|-----------------|-------|
| `dnachisel-num1` | `proto_programs/generated/dnachisel-num1/` | **`design_001.py`** (936 bp) | Skip `design_002.py`. Full outer loop **138 s** — see benchmarks. |
| `custom-egfp-lung` | `proto_programs/generated/custom-egfp-lung/` | **`design_001.py`** (720 bp) | Skip `design_002.py`. Full pool loop **79 s** — see benchmarks. |
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

Mechanical handoff gate: `uv run protofuse review <collection_id>` (checks hashes, source drift, PDB/hotspot binding, preflight). Paper-evidence failures on internal benchmark fixtures are expected until evidence quotes are added.

## Analyze program collections

- [x] Load and hash-check the `program_collection.py` handoff without importing it.
- [ ] **`dnachisel-num1`:** import and profile `design_001.py` inside `run_dnachisel_num1(tier="full")`.
- [x] Import reviewed `build_program()` entry points in a controlled analyzer.
- [x] Derive canonical signatures from model/tool identity and version, configuration,
      inputs, stochastic semantics, thresholds, weights, and optimizer position.
- [x] Record and profile observed call count, proposal count, parent latency, failures, and
      structure/logit outputs from append-only traces; unavailable accelerator, memory, and
      cost measurements remain `null`.
- [ ] Collect accelerator time, memory, cost, and decision-contribution measurements from
      real model campaigns.
- [ ] Rank recurring adjacent groups and apply exact caching/batching/shared intermediates
      before learned approximation.

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
- [ ] Package the trained surrogate and gate as the first reviewed `FusionBundle`.
- [x] Preserve immediate final full-model validation; artifacts that request another policy
      are rejected.

Raw traces and calibration data stay under `data/analysis/`; weights stay under
`data/models/`.

## Future program collections (lower priority)

CPU codon handoffs (`custom-egfp-lung`, `dnachisel-num1`) are weak fusion targets.
`gpcr-cxcr4-miniprotein` is the primary GPU-backed collection once Modal execution is
unblocked. When Phillip adds collections, prefer scenarios from
[`docs/CANDIDATE_WORKFLOWS.md`](../../../docs/CANDIDATE_WORKFLOWS.md) that repeat GPU
tools (ESMFold, Boltz-2, PARADE, AbLang) inside MCMC or pool loops.
