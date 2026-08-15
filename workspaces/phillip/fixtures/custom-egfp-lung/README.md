# CUSTOM eGFP lung fixture

Tissue-specific codon pool optimization from Hernandez-Alias et al., Genome Biology
(2023), DOI [10.1186/s13059-023-02868-2](https://doi.org/10.1186/s13059-023-02868-2).

This is the **minute-scale** counterpart to DNA Chisel's sub-second MCMC smoke
workloads. Full tier runs `n_pool=500` independent MCMC optimizations over a 720 bp
eGFP coding segment (~1–2 minutes locally).

Builder entry point: `protofuse.phillip.program_builders.run_custom_egfp_lung`.
