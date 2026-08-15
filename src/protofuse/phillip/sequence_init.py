"""Filter-safe DNA sequence initialization for MCMC workloads."""

from __future__ import annotations

import random

from proto_language.constraint import max_homopolymer_constraint
from proto_language.constraint.sequence_composition.max_homopolymer_constraint import (
    MaxHomopolymerConfig,
)
from proto_language.core import Sequence

from protofuse.phillip.dnachisel_constraints import (
    PatternAvoidanceConfig,
    pattern_avoidance_constraint,
)


def passes_homopolymer_filter(seq_str: str, *, max_length: int = 4) -> bool:
    seq = Sequence(seq_str, "dna")
    result = max_homopolymer_constraint([(seq,)], MaxHomopolymerConfig(max_length=max_length))[0]
    return float(result.score) <= 0.0


def passes_bsai_filter(seq_str: str, *, pattern: str = "GGTCTC") -> bool:
    seq = Sequence(seq_str, "dna")
    result = pattern_avoidance_constraint(
        [(seq,)],
        PatternAvoidanceConfig(pattern=pattern, max_occurrences=0),
    )[0]
    return float(result.score) <= 0.0


def passes_num1_hard_filters(
    seq_str: str,
    *,
    max_length: int = 4,
    pattern: str = "GGTCTC",
) -> bool:
    return passes_homopolymer_filter(seq_str, max_length=max_length) and passes_bsai_filter(
        seq_str, pattern=pattern
    )


def generate_filter_safe_sequence(
    length: int,
    *,
    rng: random.Random | None = None,
    max_length: int = 4,
    pattern: str = "GGTCTC",
    max_attempts: int = 10_000,
    seed: int | None = None,
) -> str:
    """Return random ACGT sequence that passes homopolymer and pattern hard filters."""

    if length < 1:
        raise ValueError("length must be >= 1")
    source = rng or random.Random(seed)
    for _ in range(max_attempts):
        candidate = "".join(source.choice("ACGT") for _ in range(length))
        if passes_num1_hard_filters(candidate, max_length=max_length, pattern=pattern):
            return candidate
    raise RuntimeError(
        f"failed to sample filter-safe sequence at length={length} after {max_attempts} attempts"
    )


def estimate_filter_pass_rate(
    length: int,
    *,
    n: int = 500,
    seed: int = 0,
    max_length: int = 4,
    pattern: str = "GGTCTC",
) -> float:
    """Monte Carlo fraction of random DNA passing homopolymer + pattern filters."""

    if length < 1:
        return 0.0
    rng = random.Random(seed)
    passed = sum(
        1
        for _ in range(n)
        if passes_num1_hard_filters(
            "".join(rng.choice("ACGT") for _ in range(length)),
            max_length=max_length,
            pattern=pattern,
        )
    )
    return passed / n
