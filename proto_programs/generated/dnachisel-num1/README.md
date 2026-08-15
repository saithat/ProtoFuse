# dnachisel-num1

Frozen program collection for **DNA Chisel Figure 1 NUM1** codon optimization
(Zaragoza et al., *Bioinformatics* 2020, DOI 10.1093/bioinformatics/btaa558).

| Program | Tier | Description |
|---------|------|-------------|
| `design_001.py` | full | Single region-local MCMC step (936 bp CDS, 200 steps) |
| `design_002.py` | smoke | Fast sanity variant (100 bp, 50 steps, 1 region pass) |

The minute-scale workload is the outer region-local loop (`max_region_passes=34`,
inner refinement) orchestrated by `run_dnachisel_num1()` in `program_builders.py`;
each `build_program()` here is one candidate generator Sai can profile and fuse.

Paper construct length is **2808 bp** (NUM1 CDS + synthesis/assembly flanks).
Preflight at 2808 bp confirms binding feasibility; executable programs use **936 bp**
(NUM1 CDS only) for gene-scale benchmarking.

Methodology fixture: `workspaces/phillip/fixtures/dnachisel-num1/methodology.json`.
