# ppi-interface-specificity fixture

Reviewed methodology for **region-local protein-protein interface specificity engineering**
(Wave 2 protein workflow). See [`docs/CANDIDATE_WORKFLOWS.md`](../../../../docs/CANDIDATE_WORKFLOWS.md).

**Handoff collection:** `proto_programs/generated/ppi-interface-specificity/`

## Seed construct

| Field | Value |
| --- | --- |
| Binder | 65-aa miniprotein (`binder_sequence`) |
| On-target | PD-L1 PDB `4ZQK`, chain A |
| Off-target | CXCR4 PDB `4RWS`, chain A |
| Interface patches | `[[18, 30], [40, 52]]` — 0-based half-open indices |

Each `region_pass` optimizes one interface patch while ESM-2 / MPNN masking fixes all
non-interface positions (same `_framework_fixed_positions` pattern as antibody CDR maturation).

## Tiers

| Tier | MCMC steps | Region passes | Generator |
| --- | --- | --- | --- |
| smoke | 20 | 1 (patch 1) | ESM-2 (`esm2_t6_8M_UR50D`) |
| full | 100 | 2 (both patches) | ProteinMPNN mutation |

Orchestrator: `run_ppi_interface_specificity(tier=...)` in `program_builders.py`.

Parameters drive `build_ppi_interface_specificity_program(params, region_pass=0)`.

## Constraints

- **structure_iptm** — binder + on-target protein (AlphaFold3)
- **boltz_binding_strength** — binder + on-target protein
- **af3_offtarget_iptm_specificity** — batched AF3 target vs off-target ipTM margin
- **structure_interface_contact** — AF2 binder template against on-target PDB

Requires Modal GPU at `program.run()` time.
