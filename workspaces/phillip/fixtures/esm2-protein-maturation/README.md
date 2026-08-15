# ESM-2 protein maturation fixture

ESM-2 masked mutation + ESMFold structure scoring for protein stability and
developability maturation. See [`docs/CANDIDATE_WORKFLOWS.md`](../../../../docs/CANDIDATE_WORKFLOWS.md).

| Tier | Segment | Steps | Seed protein |
|------|---------|-------|--------------|
| smoke | 80 aa | 50 | Truncated eGFP |
| full | 129 aa | 200 | Hen egg white lysozyme |

**Topology:** `iterative_refinement` — region-local MCMC orchestration matches
`dnachisel-num1` (`run_region_local_program` for full tier).

Builder entry point: `protofuse.phillip.program_builders.run_esm2_protein_maturation`.

**Handoff collection:** `proto_programs/generated/esm2-protein-maturation/`

Requires Modal GPU for execution (`esm2-score`, `esmfold-prediction` via constraints).
