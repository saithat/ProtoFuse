# Candidate workflows

Lower-priority backlog of paper → Proto program scenarios to add after the active
handoffs (`dnachisel-num1`, `custom-egfp-lung`). Each entry uses only components and
tools already in the pinned `proto-language` / `proto-tools` packages — no new models or
external backends required.

**Current coverage (active workflows):** 4 / 103 `proto_language` keys
(`random-nucleotide`, `mcmc`, `gc-content`, `max-homopolymer`); 0 / 140 `proto_tools`
backends invoked at runtime. Custom ProtoFuse constraints fill the rest.

**Why these matter for Sai:** Current DNA workflows are CPU-only and poor fusion targets.
Candidates below emphasize repeated GPU calls (structure prediction, LM scoring,
regulatory models) inside MCMC, pool, or cycling loops.

---

## Priority order

| Rank | Scenario ID (proposed) | Domain | Sai value | Effort |
| --- | --- | --- | --- | --- |
| 1 | `esm2-protein-maturation` | Protein | High — ESMFold every MCMC step | Low — reuses NUM1 topology |
| 2 | `freebindcraft-binder` | Protein | High — validation per candidate | Medium — new builder |
| 3 | `rfdiffusion3-boltz2-binder` | Protein | Very high — multi-tool cycling | Medium |
| 4 | `parade-utr-liver` | RNA / mRNA | High — pool × PARADE scoring | Low — reuses pool optimizer |
| 5 | `alphagenome-splice-junction` | DNA / splicing | High — variant scoring in loop | Medium |
| 6 | `antibody-cdr-maturation` | Antibody | High — region-local + AbLang | Low — reuses region solver |
| 7 | `ligandmpnn-enzyme-redesign` | Protein / ligand | Medium | Medium |
| 8 | `ppi-interface-specificity` | Protein | High — dual target/off-target AF3 | Medium |
| 9 | `symmetric-oligomer-ring` | Protein | Medium | Medium |
| 10 | `bioemu-ensemble-filter` | Protein | Medium — ensemble sampling cost | Medium |

Nucleic-acid-only candidates (`codonfm-egfp`, Borzoi/Enformer promoter design) are
deferred unless we want more DNA/RNA before protein work.

---

## Protein workflows

### 1. ESM-2 + ESMFold protein maturation

**Proposed ID:** `esm2-protein-maturation`

Refine an existing protein (GFP, lysozyme, nanobody benchmark) for stability and
developability without large functional changes.

| Role | Proto component |
| --- | --- |
| Generator | `esm2` or `semigreedy-mutation` |
| Optimizer | `mcmc` |
| Constraints | `esm2-perplexity`, `structure-plddt`, `structure-pae`, `protein-complexity`, `protein-length`, `balanced-aa` |
| Tools (via constraints) | `esmfold-prediction`, `esm2-score` |

**Topology:** `iterative_refinement` — same pattern as `dnachisel-num1`.

**Sai fusion target:** `esmfold-prediction` called on every accept/reject step.

**Smoke tier:** 50 MCMC steps, 80 aa segment. **Full tier:** 200 steps, full-length protein.

**Paper angle:** Thermostability / expression maturation benchmarks; no single canonical
paper required for a first fixture.

---

### 2. FreeBindCraft de novo binder design

**Proposed ID:** `freebindcraft-binder`

Design a mini-protein binder against a fixed target structure (PDB). PyRosetta-free
pipeline already wrapped in Proto.

| Role | Proto component |
| --- | --- |
| Generator | `freebindcraft` |
| Tools | `freebindcraft-design` |
| Constraints | `structure-iptm`, `structure-ipae`, `structure-plddt`, `pyrosetta-interface` (optional), `structure-rmsd` |
| Optimizer | `rejection-sampling` or `cycling` |

**Topology:** `staged_filter` — hallucinate → validate → filter.

**Sai fusion target:** AF2 / structure validation per candidate.

**Reference:** FreeBindCraft (2025), PyRosetta-free BindCraft alternative.

---

### 3. RFdiffusion3 + Boltz-2 binder cycling

**Proposed ID:** `rfdiffusion3-boltz2-binder`

Generate novel binder backbones, assign sequences, score binding affinity and interface
quality.

| Role | Proto component |
| --- | --- |
| Generator | `rfdiffusion-mpnn-binder` |
| Constraints | `boltz2-binding-strength`, `structure-iptm`, `esm2-perplexity`, `protein-globularity` |
| Tools | `rfdiffusion3-design`, `boltz2-prediction`, `boltz2-affinity` |
| Optimizer | `cycling` |

**Topology:** `cycling` — RFdiffusion → MPNN → fold → score → repeat.

**Sai fusion target:** `boltz2-prediction` + `structure-composite` cluster every cycle.

**Reference:** RFdiffusion3 (2025); Boltz-2 structure and affinity ([technical report](https://jeremywohlwend.com/assets/boltz2.pdf)).

---

### 4. Antibody CDR region-local optimization

**Proposed ID:** `antibody-cdr-maturation`

Refine complementarity-determining regions for naturalness and interface quality while
masking framework regions.

| Role | Proto component |
| --- | --- |
| Generator | `ablang-sample` or `esm2` on CDR segments |
| Constraints | `ablang-perplexity`, `structure-iptm`, `pyrosetta-interface`, `protein-complexity`, `gap-gini` |
| Tools | `ablang-score`, `esmfold-prediction` |
| Optimizer | `mcmc` |
| Orchestration | Reuse `region_solver.run_region_local_program` |

**Topology:** `iterative_refinement` with CDR-only masking (NUM1 pattern).

**Sai fusion target:** `ablang-score` + structure prediction per MCMC step.

---

### 5. Ligand-aware enzyme active-site redesign

**Proposed ID:** `ligandmpnn-enzyme-redesign`

Redesign residues around a bound ligand on a fixed backbone.

| Role | Proto component |
| --- | --- |
| Generator | `ligandmpnn` or `mpnn-mutation` |
| Constraints | `mpnn-sequence-probability`, `mpnn-perplexity`, `metal3d-probability` |
| Tools | `ligandmpnn-sample`, `ligandmpnn-score`, `boltz2-affinity` |
| Optimizer | `mcmc` or `cycling` |

**Topology:** `cycling` or region-local MCMC on active-site segment.

**Sai fusion target:** `ligandmpnn-score` + `boltz2-affinity` per proposal.

---

### 6. Protein–protein interface specificity engineering

**Proposed ID:** `ppi-interface-specificity`

Optimize an existing binder interface for high target binding and low off-target binding.

| Role | Proto component |
| --- | --- |
| Generator | `mpnn-mutation` or `esm2` |
| Constraints | `structure-iptm`, `boltz2-binding-strength`, `af3-offtarget-iptm-specificity`, `pyrosetta-interface`, `structure-interface-contact` |
| Optimizer | `mcmc` (region-local on interface residues) |

**Topology:** `iterative_refinement`.

**Sai fusion target:** dual target + off-target structure scoring every step.

---

### 7. Symmetric oligomer / nanoring design

**Proposed ID:** `symmetric-oligomer-ring`

Design sequences that assemble into Cn-symmetric ring multimers.

| Role | Proto component |
| --- | --- |
| Generator | `proteinmpnn` or `random-protein` |
| Constraints | `protein-symmetry-ring`, `protein-globularity`, `structure-radius-gyration`, `structure-composite`, `overall-protein-quality` |
| Optimizer | `genetic-algorithm` or `rejection-sampling` |

**Topology:** `propose_score_select` or population search.

**Sai fusion target:** symmetry + structure composite scoring on every candidate.

---

### 8. BioEmu conformational ensemble filtering

**Proposed ID:** `bioemu-ensemble-filter`

Sample conformational ensembles and select sequences that populate desired structural
states.

| Role | Proto component |
| --- | --- |
| Tools | `bioemu-sample` |
| Generator | `esm2` or `fampnn` |
| Constraints | `structure-ensemble-rmsd`, `structure-plddt` |
| Optimizer | `cycling` |

**Topology:** `cycling` — sample ensemble → score → mutate → resample.

**Sai fusion target:** `bioemu-sample` batch cost; good batching opportunity before
learned fusion.

**Reference:** BioEmu conformational ensemble ML (2024–2025).

---

## Nucleic-acid workflows (deferred)

These extend the CUSTOM / DNA Chisel line with GPU-backed objectives. Lower priority now
that `custom-egfp-lung` is complete unless we want more RNA/DNA before protein work.

### PARADE tissue-specific UTR design

**Proposed ID:** `parade-utr-liver`

| Role | Proto component |
| --- | --- |
| Constraints | `parade-utr-activity`, `parade-utr-specificity`, `parade-utr-stability` |
| Tools | `parade-activity`, `parade-gradient` |
| Optimizer | `mcmc` or pool (`run_pool_optimizer`) |

**Reference:** [Khoroshkin et al., bioRxiv 2024](https://doi.org/10.1101/2024.12.31.630783).

**Note:** Natural GPU upgrade to `custom-egfp-lung` (same tissue-specificity theme).

---

### AlphaGenome splice junction optimization

**Proposed ID:** `alphagenome-splice-junction`

| Role | Proto component |
| --- | --- |
| Constraints | `alphagenome-splice-junction`, `alphagenome-splice-site-usage`, `alphagenome-interval-track` |
| Tools | `alphagenome-score-variants`, `alphagenome-predict-sequences` |
| Optimizer | `mcmc` on intronic flanks |

**Reference:** [Avsec et al., Nature 2026](https://doi.org/10.1038/s41586-025-10014-0).

---

### CodonFM-enhanced codon optimization

**Proposed ID:** `codonfm-tissue-codon`

Replace heuristic `tissue_codon_constraint` with CodonFM fitness scoring.

| Role | Proto component |
| --- | --- |
| Tools | `codonfm-score`, `codonfm-fitness`, `codonfm-gradient` |
| Topology | Same as `custom-egfp-lung` pool |

---

### Regulatory DNA promoter design

**Proposed ID:** `borzoi-promoter-morse`

MCMC on ~200 bp promoter DNA for Morse-code chromatin accessibility patterns.

| Role | Proto component |
| --- | --- |
| Constraints | `puffin-promoter-activity`, `borzoi-track-activity`, `enformer-chromatin-accessibility-morse`, `borzoi-chromatin-accessibility-morse` |

---

## Out of scope (not in Proto inventory)

Do not spec workflows that depend on:

- ColabFold-only or custom AF2 forks without Proto wrappers
- RoseTTAFold, OmegaFold, or other structure predictors not in `proto-tools`
- RFdiffusion v1/v2 (Proto ships **RFdiffusion3**)
- Any model or tool absent from the 140-key `proto-tools` catalog

Verify keys with:

```bash
uv run python -m proto_tools.cli list
uv run python -m proto_language.cli list
```

---

## Adding a candidate

1. Pick a scenario from the priority table.
2. Add `workspaces/phillip/fixtures/<scenario-id>/methodology.json` with evidence quotes.
3. Extend `registries.py` with reviewed bindings (no unresolved names).
4. Implement builder in `program_builders.py` (or dedicated module).
5. Generate `proto_programs/generated/<scenario-id>/`, finalize, commit.
6. Register in `philip-sai-integrations/v1/catalog.json` when ready for Sai.

GPU workflows require Modal setup per [`docs/SETUP.md`](SETUP.md).
