"""Reviewed name-to-Proto-symbol maps for paper methodology compilation."""

from __future__ import annotations

DNA_BASELINE_REGISTRY: dict[str, str] = {
    "random nucleotide generator": "proto_language.generator.RandomNucleotideGenerator",
    "GC content": "proto_language.constraint.gc_content_constraint",
    "homopolymer limit": "proto_language.constraint.max_homopolymer_constraint",
    "MCMC": "proto_language.optimizer.MCMCOptimizer",
}

DNA_CHISEL_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "windowed GC content": "proto_language.constraint.gc_content_constraint",
    "BsaI site removal": "proto_language.constraint.max_homopolymer_constraint",
    "stochastic mutation generator": "proto_language.generator.RandomNucleotideGenerator",
    "MCMC refinement": "proto_language.optimizer.MCMCOptimizer",
}

DNA_CHISEL_NUM1_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "windowed GC content": "protofuse.phillip.dnachisel_constraints.sliding_window_gc_constraint",
    "BsaI site removal": "protofuse.phillip.dnachisel_constraints.pattern_avoidance_constraint",
    "k-mer uniqueness": "protofuse.phillip.dnachisel_constraints.kmer_uniqueness_constraint",
    "codon optimization": "protofuse.phillip.dnachisel_constraints.codon_usage_constraint",
    "stochastic mutation generator": "proto_language.generator.RandomNucleotideGenerator",
    "region-local MCMC refinement": "proto_language.optimizer.MCMCOptimizer",
}

CUSTOM_EGFP_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "probabilistic tissue codon generator": "proto_language.generator.RandomNucleotideGenerator",
    "tissue codon optimization": "protofuse.phillip.custom_constraints.tissue_codon_constraint",
    "GC content target": "proto_language.constraint.gc_content_constraint",
    "homopolymer filter": "proto_language.constraint.max_homopolymer_constraint",
    "pool propose-score-select": "protofuse.phillip.pool_optimizer.run_pool_optimizer",
}
