# CUSTOM eGFP lung fixture

Tissue-specific codon pool optimization from Hernandez-Alias et al., Genome Biology
(2023), DOI [10.1186/s13059-023-02868-2](https://doi.org/10.1186/s13059-023-02868-2).

The full tier uses the authors' released CUSTOM generator and metric implementations on the
paper's 239-aa eGFP input: one pool of 1,000 synonymous 717-bp coding sequences, five-metric
pool-relative ranking, rejection of homopolymers at least 7 nt long, and top-10 selection.
`design_002.py` reduces only the pool size for diagnostics and is not a reproduction result.

The result contract, paper checkpoints, thresholds, and full experiment order are documented in
[`docs/CUSTOM_REPRODUCTION.md`](../../../../docs/CUSTOM_REPRODUCTION.md).

Builder entry point: `protofuse.phillip.program_builders.run_custom_egfp_lung`.
