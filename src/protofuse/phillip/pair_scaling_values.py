"""Validated scalar values for the registered pair-scaling paper sweep."""

from __future__ import annotations

import math

PAPER_PAIR_SCALING_BETAS: tuple[float, ...] = (
    -0.75,
    -0.60,
    -0.45,
    -0.30,
    -0.15,
    0.15,
    0.30,
    0.45,
    0.60,
    0.75,
)


def validate_paper_beta(value: object) -> float:
    """Return a canonical finite paper beta or reject an unsupported setting."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("pair-scaling beta must be a number")
    beta = float(value)
    if not math.isfinite(beta):
        raise ValueError("pair-scaling beta must be finite")
    for allowed in PAPER_PAIR_SCALING_BETAS:
        if math.isclose(beta, allowed, rel_tol=0.0, abs_tol=1e-12):
            return allowed
    raise ValueError(
        f"unsupported paper pair-scaling beta {beta}; "
        f"expected one of {PAPER_PAIR_SCALING_BETAS}"
    )
