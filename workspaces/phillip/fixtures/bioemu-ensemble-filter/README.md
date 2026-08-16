# bioemu-ensemble-filter fixture

ESM-2 MCMC with BioEmu ensemble RMSD filtering against lysozyme PDB 2LYZ.

| Tier | Segment | Steps | BioEmu samples |
|------|---------|-------|----------------|
| smoke | 80 aa | 20 | 2 |
| full | 129 aa | 100 | 8 |

**Topology:** iterative refinement (MCMC proxy for cycling) — mutate → BioEmu ensemble → RMSD filter.

Builder: `protofuse.phillip.program_builders.run_bioemu_ensemble_filter`.

**Handoff collection:** `proto_programs/generated/bioemu-ensemble-filter/`
