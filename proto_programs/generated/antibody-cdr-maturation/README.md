# antibody-cdr-maturation

Frozen program collection for **region-local antibody CDR maturation** (Wave 1 protein workflow).

| Program | Tier | Description |
|---------|------|-------------|
| **`design_001.py`** | **full (primary)** | Single region-local MCMC pass (121-aa nanobody, 100 steps, 3 CDR regions) |
| `design_002.py` | smoke | Fast sanity variant (30 steps, CDR1 only, ESM-2 8M) |

## Sai: profile `design_001.py`

Each `build_program()` is one region-pass step inside `run_antibody_cdr_maturation(tier="full")`
(`max_region_passes=3`). ESM-2 mutates the active CDR only; AbLang, ESMFold ipTM, complexity,
and gap Gini score each MCMC proposal.

Methodology fixture: `workspaces/phillip/fixtures/antibody-cdr-maturation/methodology.json`.
