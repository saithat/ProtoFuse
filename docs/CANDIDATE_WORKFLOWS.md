# Candidate workflows

Living rationale for paper → Proto program scenarios. The detailed entries preserve why a
workflow was proposed even after it is implemented. Each entry uses components and tools
already in the pinned `proto-language` / `proto-tools` packages. ProtoFuse never executes
code, commands, URLs, or model identifiers copied from a paper.

As of 2026-08-15, 12 generated collections are reviewed handoffs. This includes the
previously recommended `boltz2-state-sweep` and the RFdiffusion3 + Boltz-2, LigandMPNN,
and BioEmu workflows. Three additional joint-objective collections have generated sources
but remain `reviewed=false`; source generation is not the same as a reviewed handoff or a
completed scientific run.

**Why these matter for Sai:** Current DNA workflows are CPU-only and poor fusion targets.
Candidates below emphasize repeated GPU calls (structure prediction, LM scoring,
regulatory models) inside MCMC, pool, or cycling loops.

---

## Priority order

| Rank | Scenario ID (proposed) | Domain | Sai value | Effort | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | `boltz2-state-sweep` | Protein / conformational states | Very high — Boltz-2 per sweep draw, **labelled ground truth** | Medium | Reviewed collection |
| 2 | `tm-switch-multistate` | Membrane protein | High — dual-state Boltz-2 per MCMC step | Medium | Backlog (Wave 4) |
| 3 | `rfdiffusion3-boltz2-binder` | Protein | Very high — multi-tool cycling | Medium | Reviewed collection |
| 4 | `parade-utr-liver` | RNA / mRNA | High — pool × PARADE scoring | Low — reuses pool optimizer | Backlog |
| 5 | `alphagenome-splice-junction` | DNA / splicing | High — variant scoring in loop | Medium | Backlog |
| 6 | `ligandmpnn-enzyme-redesign` | Protein / ligand | Medium | Medium | Reviewed collection |
| 7 | `bioemu-ensemble-filter` | Protein | Medium — ensemble sampling cost | Medium | Reviewed collection |
| — | `esm2-protein-maturation` | Protein | High — ESMFold every MCMC step | Low | Reviewed collection |
| — | `antibody-cdr-maturation` | Antibody | High — region-local + AbLang | Low | Reviewed collection |
| — | `freebindcraft-binder` | Protein | High — validation per candidate | Medium | Reviewed collection |
| — | `symmetric-oligomer-ring` | Protein | Medium | Medium | Reviewed collection |
| — | `ppi-interface-specificity` | Protein | High — dual target/off-target AF3 | Medium | Reviewed collection |

Reviewed rows are active collections listed in
[`src/protofuse/sai/TODO.md`](../src/protofuse/sai/TODO.md); they stay here for topology
reference only. `dnachisel-num1`, `custom-egfp-lung`, and
`gpcr-cxcr4-miniprotein` are also reviewed baseline handoffs.

Generated sources awaiting human review:

| Collection | Programs | Status boundary |
| --- | --- | --- |
| `rfdiffusion3-af3-ppi` | five full target variants + one smoke program | `reviewed=false`; not a Sai handoff |
| `af3-boltz2-state-sweep` | five full target variants + one smoke program | `reviewed=false`; not a Sai handoff |
| `evo2-enformer-borzoi` | three full regulatory patterns + one smoke program | `reviewed=false`; not a Sai handoff |

Remaining nucleic-acid-only ideas such as `codonfm-egfp` are deferred unless more DNA/RNA
coverage is needed before additional protein work.

---

## Wave 4 — conformational-state workflows

Both entries come from the same literature thread: single-structure predictors return one
dominant conformation, and the functionally interesting second state is what neither
prediction nor design reliably reaches. Candidate A predicts alternative states of
existing proteins; candidate B designs sequences that occupy two states on purpose.

### A. Boltz-2 alternative-state sweep — **reviewed collection**

**Proposed ID:** `boltz2-state-sweep`

Predict the *second* conformational state of a two-state protein by sweeping an
inference-time control over repeated predictions of one fixed sequence, then scoring every
draw against both experimental reference structures. Default inference collapses onto the
dominant state; the sweep is what surfaces the alternative one.

| Role | Proto component |
| --- | --- |
| Generator | none — the sequence is fixed; the sweep is over inference controls |
| Optimizer | `rejection-sampling` or pool (`run_pool_optimizer`) over (control value, seed) |
| Constraints | `structure-rmsd` (to each reference state), `structure-plddt`, `structure-ensemble-rmsd` |
| Tools | `boltz2-prediction`; optional `alphafold3-prediction` / `protenix-prediction` cross-check, `bioemu-sample` as ensemble baseline |

**Topology:** `propose_score_select` — enumerate sweep draws, predict, score against both
reference states, keep the ensemble.

**Sai fusion target:** `boltz2-prediction`, called once per sweep draw on an *unchanging*
sequence. The published protocol budgets 250 models per target, and the control is swept
over 10 non-zero values, so a single target is hundreds of GPU forward passes whose only
varying inputs are a scalar and a seed.

**Why this is the strongest Sai demo:**

- **Exact wins before approximation.** Every draw re-runs the trunk on identical sequence
  and MSA inputs, so caching and batching shared intermediates is a real, defensible
  speedup that needs no learned model — Sai's ordered TODO step before fusion.
- **Free, exact labels.** The teacher label is per-draw RMSD/TM-score to two deposited PDB
  structures. No wet lab, no self-referential scoring, no label noise.
- **86 natural leakage-resistant groups.** Splitting by target is the obvious grouping, and
  the benchmark already carries two subgroup axes: soluble domain motions versus membrane
  transporters, and before versus after each predictor's training cutoff.
- **Top-k recall is the native metric.** "Does the subset of draws Sai chose to actually
  run still contain the alternative state?" is exactly the top-k recall and
  risk-versus-coverage reporting in `sai/TODO.md`, with a headline number a judge
  understands: same states recovered, N× fewer Boltz-2 calls.
- **Asymmetric costs are obvious.** Missing the alternative state is a scientific failure;
  an extra forward pass is cents. That justifies a conservative gate and makes fail-closed
  fallback a feature rather than a hedge.
- **The paper's own failure mode is the fusion problem.** The response to the control is
  not monotonic — across all 86 targets none showed a strictly monotonic change in
  recovered TM-score — and the useful direction is target-specific, so without a reference
  structure the method cannot say which draw is the alternative state. Predicting that is a
  learning problem, not an arithmetic one.

**Validation data (public, no lab work):**

- IOMemP: 32 high-resolution inward- and outward-facing structures across 16 transporters,
  with construction code at <https://github.com/JingHuangLab/IOMemP>.
- The 86-target two-state set: 39 soluble domain-motion proteins plus 47 transporters.
- Published baselines to beat or match: default inference recovers 0.61 of reference states
  per state in AlphaFold 3 versus 0.73 under the swept control; earlier MSA-based ensembles
  recovered both states for only 7 of 16 IOMemP transporters (AF-depth, 255 models per
  sequence) and 3 of 16 (AF-cluster).
- Metrics: per-state success at 2 Å, worst-case minimum RMSD, fill ratio between states.

**Feasibility — two tiers.** The published control multiplies the latent pair
representation at the Pairformer input, which `boltz2-prediction` does not expose.

- *Tier 1 (no fork, do this first):* sweep only exposed knobs — seed, diffusion samples,
  recycles, and MSA subsampling depth. MSA subsampling is a documented alternative-state
  lever that acts purely through inputs, and combining it with the internal control was
  what recovered the harder Boltz-2 metrics, so it is a legitimate standalone axis.
- *Tier 2 (stretch):* `proto-tools eject-standalone` the Boltz-2 backend and add the scalar
  at the Pairformer input. Only attempt after Tier 1 profiles cleanly.

**Smoke tier:** 1 IOMemP transporter, 3 control values × 2 seeds.
**Full tier:** 5 targets (mixed transporter + domain motion), 11 control values × 5 seeds.

**Reference:** Suzuki & Amagasa, "Biasing Conformational Sampling in AlphaFold 3 and
Boltz-2 via Pair Representation Scaling," [bioRxiv 2026](https://doi.org/10.64898/2026.01.23.701250)
· benchmark dataset: Xie & Huang, [*J. Chem. Inf. Model.* 64, 3524–3536 (2024)](https://doi.org/10.1021/acs.jcim.3c01936).

---

### B. Dual-state transmembrane switch design

**Proposed ID:** `tm-switch-multistate`

Optimize a transmembrane helical dimer sequence so it is compatible with *two* target
conformations at once, with a tunable preference between them — the design analogue of
candidate A. Membrane protein design is where deep learning is furthest behind: TM
interfaces are held together by weak polar and backbone-directed contacts that sequential
structure-then-sequence pipelines cannot model, which is why the activity cycles of
channels and transporters remain largely out of reach.

| Role | Proto component |
| --- | --- |
| Generator | `esm2` or `mpnn-mutation` on the TM segment |
| Optimizer | `mcmc`, region-local on the TM interface (`run_region_local_program`) |
| Constraints | `structure-rmsd` against **both** reference states, `structure-iptm`, `structure-plddt`, `protein-complexity` |
| Tools | `boltz2-prediction` (or `alphafold3-prediction`) scored twice per step, once per target state |

**Topology:** `iterative_refinement` with a state-selective objective — reward sequences
whose predicted structures satisfy both states, penalize collapse onto either one.

**Sai fusion target:** two structure predictions per accepted/rejected MCMC proposal, the
same dual-call shape as `ppi-interface-specificity` but with two conformations of one
target instead of two different targets.

**Why it ranks second for Sai, despite being the better science story:** there is no
ground-truth label available inside a hackathon. The source paper's readouts are
cell-based dimerization assays, pSTAT5 signalling, and steered-MD free-energy barriers;
none are reproducible here, and steered MD is far too expensive to serve as a teacher.
Sai would be training a surrogate against his own structure predictions, which makes the
risk-versus-coverage curve much harder to defend. Build it *after* candidate A, which
supplies the same "score a sequence against two reference states" machinery.

**Backend constraint:** TMDiffusion has no `proto-tools` key, so it cannot be bound (see
*Out of scope* below). This workflow reimplements the paper's *multi-state objective* —
conditioning on both states throughout optimization rather than intersecting sequence pools
afterwards — using in-catalog tools only. Record the model substitution in the fixture's
`unknowns`.

**Smoke tier:** 30 MCMC steps, one TM dimer, 2 states.
**Full tier:** 100 steps, 3 designs per state preference.

**References:** Rudden et al., "Deep learning-based joint sequence–structure de novo
membrane protein design" (TMDiffusion), [bioRxiv 2025](https://doi.org/10.1101/2025.08.15.670493)
· Jojoa-Cruz et al., "De novo design of transmembrane accessory subunits for fold
stabilization and expansion," [bioRxiv 2026](https://doi.org/10.64898/2026.05.14.725059)
· Montalvillo Ortega et al., "Generative Landscapes and Dynamics to Design Multidomain
Artificial Transmembrane Transporters," [bioRxiv 2025](https://doi.org/10.1101/2025.03.28.645293).

---

### Surrogate design prior art (Sai reading, not a workflow)

Sengar et al., "Beyond Ensembles: Simulating All-Atom Protein Dynamics in a Learned Latent
Space," [arXiv:2509.02196](https://arxiv.org/abs/2509.02196) — an encoder–propagator–decoder
surrogate that replaces MD in a learned latent space and recovers a GPCR activation
surface. Same lab as TMDiffusion, and the closest published statement of ProtoFuse's own
thesis; useful prior art to cite when justifying the surrogate architecture.

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

## Nucleic-acid workflows

These extend the CUSTOM / DNA Chisel line with GPU-backed objectives. PARADE,
AlphaGenome, and CodonFM remain backlog ideas. The related Evo 2 + Enformer + Borzoi
joint-objective sources have been generated, but their collection remains unreviewed.

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

The implemented related collection is `evo2-enformer-borzoi`: three full Morse-pattern
programs plus one smoke program. Its manifest currently says `reviewed=false`, so this is
generator coverage rather than an active handoff or completed model run.

---

## Out of scope (not in Proto inventory)

Do not spec workflows that depend on:

- ColabFold-only or custom AF2 forks without Proto wrappers
- RoseTTAFold, OmegaFold, or other structure predictors not in `proto-tools`
- RFdiffusion v1/v2 (Proto ships **RFdiffusion3**)
- TMDiffusion, LD-FPG/GLDP, and other published models without a `proto-tools` key —
  reimplement their *objective* with in-catalog tools instead, and record the substitution
  in `unknowns`
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
