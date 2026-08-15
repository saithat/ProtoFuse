"""Reviewed name-to-Proto-symbol maps for integration scenarios."""

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
