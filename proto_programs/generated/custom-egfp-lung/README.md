# custom-egfp-lung

Frozen program collection for **CUSTOM** tissue-specific eGFP codon pool optimization
(Hernandez-Alias et al., *Genome Biology* 2023, DOI 10.1186/s13059-023-02868-2).

| Program | Tier | Description |
|---------|------|-------------|
| `design_001.py` | full | Single pool-member MCMC program (720 bp, 100 steps) |
| `design_002.py` | smoke | Fast sanity variant (720 bp, 20 steps) |

The minute-scale workload is the outer pool loop (`n_pool=1000`) orchestrated by
`run_custom_egfp_lung()` in `program_builders.py`; each `build_program()` here is one
candidate generator Sai can profile and fuse.

Methodology fixture: `workspaces/phillip/fixtures/custom-egfp-lung/methodology.json`.
