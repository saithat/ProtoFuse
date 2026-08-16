# custom-egfp-lung

Frozen program collection for **CUSTOM** tissue-specific eGFP codon pool optimization
(Hernandez-Alias et al., *Genome Biology* 2023, DOI 10.1186/s13059-023-02868-2).

| Program | Tier | Description |
|---------|------|-------------|
| `design_001.py` | full | Paper-scale 717-bp eGFP workflow: 1,000 candidates, five CUSTOM metrics, homopolymer filtering, top 10 |
| `design_002.py` | smoke | Reduced 30-candidate software diagnostic; not reproduction evidence |

`design_001.py` is one complete released-CUSTOM-style pool, not one MCMC member. Use the
same-pool parity artifact before collecting Proto or ProtoFuse results, and keep the paper's
historical results separate from newly paired seeds.

Methodology fixture: `workspaces/phillip/fixtures/custom-egfp-lung/methodology.json`.
Experiment contract: `docs/CUSTOM_REPRODUCTION.md`.
