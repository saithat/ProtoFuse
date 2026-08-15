# antibody-cdr-maturation fixture

Reviewed methodology for **region-local antibody CDR maturation** (Wave 1 protein workflow).
See [`docs/CANDIDATE_WORKFLOWS.md`](../../../../docs/CANDIDATE_WORKFLOWS.md) for scenario rationale.

**Handoff collection:** `proto_programs/generated/antibody-cdr-maturation/`

## Seed construct

| Field | Value |
| --- | --- |
| Framework | 121-aa anti-GFP nanobody VHH (`framework_sequence`) |
| CDR regions | `[[26, 38], [55, 65], [95, 103]]` — 0-based half-open indices |
| Antigen stub | 19-aa peptide (`target_antigen_sequence`) for smoke-tier ipTM |

CDR boundaries follow approximate IMGT numbering on the compact VHH domain. Each
`region_pass` optimizes one CDR while ESM-2 masking fixes all framework positions plus
inactive CDRs.

## Tiers

| Tier | MCMC steps | Region passes | ESM-2 checkpoint |
| --- | --- | --- | --- |
| smoke | 30 | 1 (CDR1 only) | `esm2_t6_8M_UR50D` |
| full | 100 | 3 (CDR1→CDR3) | `esm2_t33_650M_UR50D` |

Orchestrator: `run_antibody_cdr_maturation(tier=...)` in `program_builders.py`.

Parameters drive `build_antibody_cdr_maturation_program(params, region_pass=0)`.
