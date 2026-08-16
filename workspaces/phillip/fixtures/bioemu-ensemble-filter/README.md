# bioemu-ensemble-filter fixture

ESM-2 MCMC that jointly minimizes BioEmu ensemble-similarity energy against
lysozyme PDB 2LYZ and score-only ESMFold confidence energy.

| Tier | Segment | Steps | BioEmu samples |
|------|---------|-------|----------------|
| smoke | 80 aa | 5 | 1 |
| full | 129 aa | 100 | 8 |

**Topology:** iterative refinement — mutate → score the same candidate with BioEmu
and ESMFold → jointly accept or reject. The 4 Å RMSD and pLDDT 70 values are
reporting targets, not hard constraints.

Builder: `protofuse.phillip.program_builders.run_bioemu_ensemble_filter`.

**Handoff collection:** `proto_programs/generated/bioemu-ensemble-filter/`
