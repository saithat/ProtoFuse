# ligandmpnn-enzyme-redesign fixture

LigandMPNN active-site MCMC on carbonic anhydrase II holo structure PDB 3HTB.

| Tier | Steps | Mutations/step |
|------|-------|----------------|
| smoke | 20 | 2 |
| full | 100 | 3 |

**Topology:** region-local MCMC on active-site ordinals with ESMFold developability gating.

Builder: `protofuse.phillip.program_builders.run_ligandmpnn_enzyme_redesign`.

**Handoff collection:** `proto_programs/generated/ligandmpnn-enzyme-redesign/`
