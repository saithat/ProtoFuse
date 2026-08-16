# freebindcraft-binder fixture

PyRosetta-free de novo mini-protein binder design against a fixed target structure
using FreeBindCraft. See [`docs/CANDIDATE_WORKFLOWS.md`](../../../../docs/CANDIDATE_WORKFLOWS.md).

| Tier | Binder length | Samples | Target |
|------|---------------|---------|--------|
| smoke | 50 aa | 5 | PDB 4RWS chain A |
| full | 70 aa | 50 | PDB 4RWS chain A |

**Topology:** `staged_filter` — FreeBindCraft hallucination followed by AF2 structure
validation and rejection sampling.

Builder entry point: `protofuse.phillip.program_builders.run_freebindcraft_binder`.

**Handoff collection:** `proto_programs/generated/freebindcraft-binder/`

Requires Modal GPU for execution (`freebindcraft-design`, `alphafold2-prediction` via
generator and constraints).
