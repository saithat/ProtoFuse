# rfdiffusion3-boltz2-binder fixture

RFdiffusion3 bootstrap + ProteinMPNN cycling with Boltz-2 scoring against PDB 4RWS.

| Tier | Binder length | Cycles | Target |
|------|---------------|--------|--------|
| smoke | 50 aa | 2 | PDB 4RWS chain A |
| full | 70 aa | 10 | PDB 4RWS chain A |

**Topology:** `cycling` — RFdiffusion3+MPNN bootstrap, then Boltz-2 fold → MPNN redesign loops.

Builder: `protofuse.phillip.program_builders.run_rfdiffusion3_boltz2_binder`.

**Handoff collection:** `proto_programs/generated/rfdiffusion3-boltz2-binder/`
