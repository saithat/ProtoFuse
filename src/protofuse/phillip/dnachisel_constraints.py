"""Paper-faithful DNA Chisel constraints for the NUM1 gene-scale workload."""

from __future__ import annotations

import random
from typing import Literal

from proto_language.constraint.constraint_registry import constraint
from proto_language.core import ConstraintOutput, Sequence
from proto_language.utils import MAX_ENERGY, calculate_percentage_range_deviation
from proto_language.utils.base import BaseConfig, ConfigField

_FRACTIONAL_EPSILON = 1e-9

_ECOLI_CODON_USAGE: dict[str, float] = {
    "TTT": 22.7,
    "TTC": 15.9,
    "TTA": 13.5,
    "TTG": 13.5,
    "TCT": 7.0,
    "TCC": 7.0,
    "TCA": 7.0,
    "TCG": 7.0,
    "TAT": 15.7,
    "TAC": 15.7,
    "TAA": 2.0,
    "TAG": 2.0,
    "TGT": 4.5,
    "TGC": 4.5,
    "TGA": 0.5,
    "TGG": 10.5,
    "CTT": 10.9,
    "CTC": 10.9,
    "CTA": 3.9,
    "CTG": 52.7,
    "CCT": 6.8,
    "CCC": 6.8,
    "CCA": 6.8,
    "CCG": 6.8,
    "CAT": 12.4,
    "CAC": 12.4,
    "CAA": 14.0,
    "CAG": 28.7,
    "CGT": 21.9,
    "CGC": 21.9,
    "CGA": 3.2,
    "CGG": 3.2,
    "ATT": 29.4,
    "ATC": 29.4,
    "ATA": 4.9,
    "ATG": 26.8,
    "ACT": 8.9,
    "ACC": 23.7,
    "ACA": 6.4,
    "ACG": 8.9,
    "AAT": 16.6,
    "AAC": 20.5,
    "AAA": 72.4,
    "AAG": 27.6,
    "AGT": 7.0,
    "AGC": 15.7,
    "AGA": 1.9,
    "AGG": 1.9,
    "GTT": 17.0,
    "GTC": 14.5,
    "GTA": 10.9,
    "GTG": 25.4,
    "GCT": 17.5,
    "GCC": 25.4,
    "GCA": 20.0,
    "GCG": 33.7,
    "GAT": 31.9,
    "GAC": 31.9,
    "GAA": 39.5,
    "GAG": 18.5,
    "GGT": 24.9,
    "GGC": 29.7,
    "GGA": 7.8,
    "GGG": 7.8,
}

_REFERENCE_KMERS: dict[tuple[int, int, int], set[str]] = {}


class SlidingWindowGCConfig(BaseConfig):
    min_gc: float = ConfigField(
        ge=0, le=100, title="Min GC", description="Minimum GC percent per window"
    )
    max_gc: float = ConfigField(
        ge=0, le=100, title="Max GC", description="Maximum GC percent per window"
    )
    window_bp: int = ConfigField(
        ge=1, title="Window size (bp)", description="Sliding window length in bp"
    )


class PatternAvoidanceConfig(BaseConfig):
    pattern: str = ConfigField(title="Pattern to avoid", description="DNA motif to limit")
    max_occurrences: int = ConfigField(
        default=0,
        ge=0,
        title="Max allowed occurrences",
        description="Maximum allowed motif count",
    )


class KmerUniquenessConfig(BaseConfig):
    k: int = ConfigField(
        ge=2, le=8, title="K-mer length", description="K-mer length for uniqueness scan"
    )
    max_frequency: float = ConfigField(
        default=0.02,
        ge=0.0,
        le=1.0,
        title="Max frequency for any single k-mer",
        description="Maximum allowed frequency for any k-mer",
    )


class CodonUsageConfig(BaseConfig):
    target_organism: Literal["escherichia_coli"] = ConfigField(
        default="escherichia_coli",
        title="Target organism",
        description="Organism for codon usage table",
    )
    min_relative_usage: float = ConfigField(
        default=0.15,
        ge=0.0,
        le=1.0,
        title="Minimum relative usage vs optimal codon per position",
        description="Minimum acceptable relative codon usage score",
    )


class ReferenceHomologyConfig(BaseConfig):
    k: int = ConfigField(
        ge=4,
        le=8,
        title="K-mer length",
        description="K-mer length for homology detection",
    )
    reference_length_bp: int = ConfigField(
        default=50000,
        ge=1000,
        title="Reference length",
        description="Length of simulated reference sequence",
    )
    max_homology_hits: int = ConfigField(
        default=0,
        ge=0,
        title="Max homology hits",
        description="Maximum allowed k-mer matches against reference",
    )
    reference_seed: int = ConfigField(
        default=42,
        title="Reference seed",
        description="Seed for deterministic reference sequence generation",
    )


def _count_overlapping(seq_str: str, pattern: str) -> int:
    if not pattern:
        return 0
    count = 0
    start = 0
    while True:
        pos = seq_str.find(pattern, start)
        if pos == -1:
            return count
        count += 1
        start = pos + 1


def _iter_kmer_counts(seq_str: str, k: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    if len(seq_str) < k:
        return counts
    for index in range(len(seq_str) - k + 1):
        kmer = seq_str[index : index + k]
        counts[kmer] = counts.get(kmer, 0) + 1
    return counts


def _iter_kmers(seq_str: str, k: int) -> list[str]:
    if len(seq_str) < k:
        return []
    return [seq_str[index : index + k] for index in range(len(seq_str) - k + 1)]


def _reference_kmers(k: int, *, reference_length_bp: int, reference_seed: int) -> set[str]:
    cache_key = (k, reference_length_bp, reference_seed)
    if cache_key not in _REFERENCE_KMERS:
        rng = random.Random(reference_seed)
        reference = "".join(rng.choice("ACGT") for _ in range(reference_length_bp))
        kmers = {reference[index : index + k] for index in range(len(reference) - k + 1)}
        _REFERENCE_KMERS[cache_key] = kmers
    return _REFERENCE_KMERS[cache_key]


@constraint(
    key="sliding-window-gc",
    label="Sliding Window GC",
    config=SlidingWindowGCConfig,
    description="Enforce GC bounds on every sliding window",
    tools_called=[],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def sliding_window_gc_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: SlidingWindowGCConfig,
) -> list[ConstraintOutput]:
    results: list[ConstraintOutput] = []
    for (seq,) in input_sequences:
        seq_str = seq.sequence.upper()
        if len(seq_str) < config.window_bp:
            results.append(
                ConstraintOutput(
                    score=MAX_ENERGY,
                    metadata={"window_violations": 1, "worst_gc": 0.0},
                )
            )
            continue

        worst_deviation = 0.0
        violations = 0
        worst_gc = 0.0
        for start in range(len(seq_str) - config.window_bp + 1):
            window = seq_str[start : start + config.window_bp]
            gc = 100.0 * sum(nt in "GC" for nt in window) / config.window_bp
            deviation = calculate_percentage_range_deviation(gc, config.min_gc, config.max_gc)
            if deviation > 0:
                violations += 1
            if deviation > worst_deviation:
                worst_deviation = deviation
                worst_gc = gc

        results.append(
            ConstraintOutput(
                score=min(MAX_ENERGY, worst_deviation),
                metadata={"window_violations": violations, "worst_gc": worst_gc},
            )
        )
    return results


@constraint(
    key="pattern-avoidance",
    label="Pattern Avoidance",
    config=PatternAvoidanceConfig,
    description="Limit occurrences of a DNA motif",
    tools_called=[],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def pattern_avoidance_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: PatternAvoidanceConfig,
) -> list[ConstraintOutput]:
    pattern = config.pattern.upper()
    results: list[ConstraintOutput] = []
    for (seq,) in input_sequences:
        seq_str = seq.sequence.upper()
        count = _count_overlapping(seq_str, pattern)
        excess = max(0, count - config.max_occurrences)
        score = min(1.0, excess * 0.25) if excess else 0.0
        results.append(
            ConstraintOutput(
                score=score,
                metadata={"pattern_count": count, "pattern": pattern},
            )
        )
    return results


@constraint(
    key="kmer-uniqueness",
    label="K-mer Uniqueness",
    config=KmerUniquenessConfig,
    description="Penalize overrepresented k-mers across the sequence",
    tools_called=[],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def kmer_uniqueness_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: KmerUniquenessConfig,
) -> list[ConstraintOutput]:
    results: list[ConstraintOutput] = []
    for (seq,) in input_sequences:
        seq_str = seq.sequence.upper()
        counts = _iter_kmer_counts(seq_str, config.k)
        total_positions = max(len(seq_str) - config.k + 1, 1)
        worst_frequency = 0.0
        worst_kmer = ""
        for kmer, count in counts.items():
            frequency = count / total_positions
            if frequency > worst_frequency:
                worst_frequency = frequency
                worst_kmer = kmer

        if worst_frequency <= config.max_frequency:
            score = 0.0
        else:
            score = min(
                1.0,
                (worst_frequency - config.max_frequency)
                / max(config.max_frequency, _FRACTIONAL_EPSILON),
            )
        results.append(
            ConstraintOutput(
                score=score,
                metadata={
                    "worst_kmer": worst_kmer,
                    "worst_frequency": worst_frequency,
                    "unique_kmers": len(counts),
                },
            )
        )
    return results


@constraint(
    key="codon-usage",
    label="Codon Usage",
    config=CodonUsageConfig,
    description="Score codon usage relative to E. coli preferences",
    tools_called=[],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def codon_usage_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: CodonUsageConfig,
) -> list[ConstraintOutput]:
    del config
    usage = _ECOLI_CODON_USAGE
    max_usage = max(usage.values())

    results: list[ConstraintOutput] = []
    for (seq,) in input_sequences:
        seq_str = seq.sequence.upper()
        codon_count = len(seq_str) // 3
        if codon_count == 0:
            results.append(
                ConstraintOutput(score=MAX_ENERGY, metadata={"mean_relative_usage": 0.0})
            )
            continue

        relative_scores: list[float] = []
        for index in range(codon_count):
            codon = seq_str[index * 3 : index * 3 + 3]
            if len(codon) < 3 or any(base not in "ACGT" for base in codon):
                relative_scores.append(0.0)
                continue
            codon_usage = usage.get(codon, 1.0)
            relative_scores.append(codon_usage / max_usage)

        mean_relative = sum(relative_scores) / len(relative_scores)
        score = min(1.0, max(0.0, 1.0 - mean_relative))
        results.append(
            ConstraintOutput(
                score=score,
                metadata={"mean_relative_usage": mean_relative, "codons_scored": codon_count},
            )
        )
    return results


@constraint(
    key="reference-homology",
    label="Reference Homology",
    config=ReferenceHomologyConfig,
    description="Penalize k-mers that appear in a simulated yeast reference sequence",
    tools_called=[],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def reference_homology_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: ReferenceHomologyConfig,
) -> list[ConstraintOutput]:
    reference = _reference_kmers(
        config.k,
        reference_length_bp=config.reference_length_bp,
        reference_seed=config.reference_seed,
    )
    results: list[ConstraintOutput] = []
    for (seq,) in input_sequences:
        seq_str = seq.sequence.upper()
        kmers = _iter_kmers(seq_str, config.k)
        hits = sum(1 for kmer in kmers if kmer in reference)
        excess = max(0, hits - config.max_homology_hits)
        score = min(1.0, excess / max(len(kmers), 1))
        results.append(
            ConstraintOutput(
                score=score,
                metadata={"homology_hits": hits, "k": config.k},
            )
        )
    return results
