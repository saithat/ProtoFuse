# esm2-protein-maturation

Frozen program collection for **ESM-2 + ESMFold** protein maturation
(developability / stability refinement benchmark).

| Program | Tier | Description |
|---------|------|-------------|
| `design_001.py` | full | Lysozyme maturation (129 aa, 200 MCMC steps) |
| `design_002.py` | smoke | Truncated eGFP segment (80 aa, 50 MCMC steps) |

Methodology fixture: `workspaces/phillip/fixtures/esm2-protein-maturation/methodology.json`.

Validate: `uv run protofuse collection validate esm2-protein-maturation`

Requires Modal GPU for execution (`esm2-score`, `esmfold-prediction`).
