# dnachisel-num1

Frozen program collection for **DNA Chisel Figure 1 NUM1** codon optimization
(Zaragoza et al., *Bioinformatics* 2020, DOI 10.1093/bioinformatics/btaa558).

| Program | Tier | Description |
|---------|------|-------------|
| **`design_001.py`** | **full (primary)** | Single region-local MCMC step (936 bp CDS, 200 steps) |
| `design_002.py` | smoke | Fast sanity variant (100 bp, 50 steps, 1 region pass) |

## Sai: profile `design_001.py`

**Focus on `design_001.py` (936 bp).** Skip `design_002.py` — it is a shortened smoke
check only and does not represent the gene-scale NUM1 workload.

Phillip validated the minute-scale outer loop on 2026-08-15:

```bash
uv run protofuse run dnachisel-num1 --tier full
# wall_ms=112784 (~1.9 min), output length=936 bp
```

Orchestrator: `run_dnachisel_num1(tier="full")` in `program_builders.py`
(`max_region_passes=34`, inner refinement). Each `build_program()` in this collection is
one inner MCMC step Sai should profile inside that loop.

The minute-scale workload is the outer region-local loop (`max_region_passes=34`,
inner refinement) orchestrated by `run_dnachisel_num1()` in `program_builders.py`;
each `build_program()` here is one candidate generator Sai can profile and fuse.

Paper construct length is **2808 bp** (NUM1 CDS + synthesis/assembly flanks).
Preflight at 2808 bp confirms binding feasibility; executable programs use **936 bp**
(NUM1 CDS only) for gene-scale benchmarking.

Methodology fixture: `workspaces/phillip/fixtures/dnachisel-num1/methodology.json`.
