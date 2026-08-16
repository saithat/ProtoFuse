# Symmetric oligomer ring fixture

Cn-symmetric homo-oligomer ring design from [`docs/CANDIDATE_WORKFLOWS.md`](../../../../docs/CANDIDATE_WORKFLOWS.md).

| Tier | Symmetry | Pool | Monomer length | Inner samples |
|------|----------|------|----------------|---------------|
| smoke | C3 | 100 | 60 aa | 5 |
| full | C6 | 1000 | 80 aa | 20 |

**Topology:** `propose_score_select` — inner `RejectionSamplingOptimizer` per pool member,
outer `run_pool_optimizer` (same pattern as `custom-egfp-lung`).

Builder entry point: `protofuse.phillip.program_builders.run_symmetric_oligomer_ring`.

**Handoff collection:** `proto_programs/generated/symmetric-oligomer-ring/`

Requires Modal GPU for execution (`esmfold-prediction` via structure constraints).
