# ligandmpnn-enzyme-redesign fixture

Joint LigandMPNN probability-loss and score-only ESMFold confidence optimization
on carbonic anhydrase II holo structure PDB 3HTB.

| Tier | Steps | Mutations/step |
|------|-------|----------------|
| smoke | 5 | 1 |
| full | 100 | 1 |

**Topology:** seeded non-identity mutation on active-site ordinals followed by MCMC,
with both parent-model
energies evaluated on the same candidate and pLDDT 70 retained as a reporting target.

Builder: `protofuse.phillip.program_builders.run_ligandmpnn_enzyme_redesign`.

**Handoff collection:** `proto_programs/generated/ligandmpnn-enzyme-redesign/`
