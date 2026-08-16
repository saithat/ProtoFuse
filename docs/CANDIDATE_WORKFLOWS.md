# Candidate workflows

Living rationale for paper → Proto program scenarios. The detailed entries preserve why a
workflow was proposed even after it is implemented. Each entry uses components and tools
already in the pinned `proto-language` / `proto-tools` packages. ProtoFuse never executes
code, commands, URLs, or model identifiers copied from a paper.

As of 2026-08-16, 14 collection manifests say `reviewed=true`, but only
`custom-egfp-lung`, `dnachisel-num1`, `evo2-enformer-borzoi`, and
`rfdiffusion3-af3-ppi` pass the complete mechanical handoff gate. Manifest approval, a
`READY FOR HANDOFF` review, paper verification, and a completed scientific run are distinct
states; experiments may start only after the applicable gates pass.

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

Rows labelled “Reviewed collection” reflect the manifest flag and stay here for topology
reference; they are active only when the mechanical gate also prints `READY FOR HANDOFF`.
See [`src/protofuse/sai/TODO.md`](../src/protofuse/sai/TODO.md). `dnachisel-num1` and
`custom-egfp-lung` are READY baseline handoffs; `gpcr-cxcr4-miniprotein` remains mechanically
blocked despite its manifest flag.

New joint-objective collection status:

| Collection | Programs | Status boundary |
| --- | --- | --- |
| `evo2-enformer-borzoi` | three full regulatory patterns + one smoke program | Approved; handoff and paper gates pass. Full Evo2 exhausted H100 and H200 memory. A repo-owned service now follows Arc's NVIDIA 25.04 container route on one B200; deployment and a full-length call remain the execution gates. |
| `rfdiffusion3-af3-ppi` | five full target variants + one smoke program | Approved; handoff and paper gates pass. Execution is blocked because the AF3 backend is not available on Modal or this host. |
| `af3-boltz2-state-sweep` | 50 full target/scale variants + one smoke program | The required benchmark is pair-scaled, query-only Boltz-2, so neither AF3 parameters nor a user-held MSA blocks smoke or handoff. Proto and ProtoFuse must receive identical backend inputs, beta, seed, and proposal order. Pinned AF3 v3.0.1 plus the paper-matched MSA remain optional fidelity checks. Query-only results are not paper-accuracy reproductions. Still `reviewed=false`; not a Sai handoff. |

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

The implemented fixed-sequence collection is deliberately narrower: it validates the
pair-scaling hook, batching/cache behavior, fail-closed execution, and a paired Proto versus
ProtoFuse throughput measurement. It is **not** a learned-surrogate accuracy benchmark and
is not the primary fusion benchmark. That evaluation needs varied sequence proposals or
independent trajectories, held-out full-model labels, and identical backend inputs, seeds,
and proposal order in both arms.

**Why a broader varied-target version could become a strong Sai demo:**

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

**Feasibility — two fidelity tiers.** The published control multiplies the latent pair
representation at the Pairformer input. ProtoFuse now provides an audited, fail-closed
Boltz-2 pre-hook for that intervention.

- *Required runnable tier:* pair-scaled Boltz-2 with query-only inputs. Use the exact same
  sequence batch, beta, model seed, diffusion count, and proposal order for Proto and
  ProtoFuse. This removes AF3 weights and a user-held server MSA from the gate, but the
  resulting accuracy may differ materially from the paper.
- *Optional fidelity tier:* supply the exact user-held AlphaFold Server MSA at depth 1024
  and explicitly opt into pinned AlphaFold 3 v3.0.1 alongside Boltz-2. This is useful for
  reproduction checks but is not required for smoke, review, or paired throughput work.

**Smoke tier:** adenylate kinase, one beta, one seed, one query-only Boltz-2 draw.
**Full tier:** adenylate kinase, 10 beta values × 5 seeds × 5 query-only Boltz-2 draws.

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
| Generator | seeded `semigreedy-mutation` restricted to active-site ordinals |
| Constraints | `mpnn-sequence-probability`, score-only `structure-plddt`, fixed protein length |
| Parent model families | `ligandmpnn-score`, `esmfold-prediction` |
| Optimizer | `mcmc` or `cycling` |

**Topology:** `cycling` or region-local MCMC on active-site segment.

**Sai fusion target:** one aligned two-output group containing LigandMPNN probability
loss and ESMFold confidence on the same active-site variant. See
[`LIGANDMPNN_ESMFOLD_EXPERIMENT.md`](LIGANDMPNN_ESMFOLD_EXPERIMENT.md).

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
| Parent model families | `bioemu-sample`, `esmfold-prediction` |
| Generator | `esm2` or `fampnn` |
| Constraints | `structure-ensemble-rmsd`, `structure-plddt` |
| Optimizer | `cycling` |

**Topology:** `cycling` — sample ensemble → score → mutate → resample.

**Sai fusion target:** one aligned two-output group containing BioEmu ensemble
similarity and ESMFold confidence on the same variable sequence. The score-only
ESMFold adapter discards an unused structure side output; mandatory final validation
still reruns both parents. See [`BIOEMU_ESMFOLD_EXPERIMENT.md`](BIOEMU_ESMFOLD_EXPERIMENT.md).

**Reference:** BioEmu conformational ensemble ML (2024–2025).

---

## Nucleic-acid workflows

These extend the CUSTOM / DNA Chisel line with GPU-backed objectives. PARADE,
AlphaGenome, and CodonFM remain backlog ideas. The related Evo 2 + Enformer + Borzoi
joint-objective collection is reviewed and passes both handoff gates; its full runtime status is
tracked in [`EVO2_REPRODUCTION.md`](EVO2_REPRODUCTION.md).

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
programs plus one smoke program. Its manifest is reviewed and its mechanical and paper gates
pass. See [`EVO2_REPRODUCTION.md`](EVO2_REPRODUCTION.md) for the runtime gate and experiment
order; only the three full programs produce paper-comparable results.

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
