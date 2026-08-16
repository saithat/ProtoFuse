"""Paired full-versus-fused execution with identical program seeds."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Literal

from proto_language.core import Program
from proto_language.core.optimizer import derive_seeds

from protofuse.sai.transform import transform_with_artifact


@dataclass(frozen=True)
class PairedRun:
    seed: int
    full_seconds: float
    fused_seconds: float
    speedup: float
    identical_sequences: bool
    maximum_energy_difference: float
    surrogate_routes: int
    full_model_routes: int


@dataclass(frozen=True)
class PairedEvaluation:
    runs: tuple[PairedRun, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": [asdict(run) for run in self.runs],
            "mean_speedup": sum(run.speedup for run in self.runs) / len(self.runs),
            "all_final_sequences_identical": all(run.identical_sequences for run in self.runs),
            "maximum_energy_difference": max(run.maximum_energy_difference for run in self.runs),
        }


def _apply_seed(program: Program, seed: int) -> None:
    program.seed = seed
    for optimizer, derived in zip(
        program.optimizers,
        derive_seeds(seed, len(program.optimizers)),
        strict=True,
    ):
        optimizer.seed = derived


def _outputs(program: Program) -> tuple[tuple[str, ...], tuple[float, ...]]:
    sequences = tuple(
        sequence.sequence
        for construct in program.constructs
        for sequence in construct.joined_sequences
    )
    return sequences, tuple(float(value) for value in program.energy_scores)


def evaluate_paired(
    build_program: Callable[[], Program],
    artifact: Any,
    *,
    seeds: Sequence[int],
    device: Literal["modal"] | None = None,
) -> PairedEvaluation:
    if not seeds:
        raise ValueError("paired evaluation requires at least one seed")
    runs: list[PairedRun] = []
    for seed in seeds:
        full = build_program()
        fused = transform_with_artifact(build_program(), artifact)
        _apply_seed(full, seed)
        _apply_seed(fused, seed)

        started = perf_counter()
        full.run(device=device)
        full_seconds = perf_counter() - started
        full_sequences, full_energies = _outputs(full)

        started = perf_counter()
        fused.run(device=device)
        fused_seconds = perf_counter() - started
        fused_sequences, fused_energies = _outputs(fused)

        if len(full_energies) != len(fused_energies):
            maximum_difference = float("inf")
        else:
            differences = [
                abs(left - right)
                for left, right in zip(full_energies, fused_energies, strict=True)
                if math.isfinite(left) and math.isfinite(right)
            ]
            maximum_difference = max(differences, default=0.0)
        evaluators = getattr(fused, "_protofuse_evaluators", ())
        surrogate_routes = sum(item.routing_counts["surrogate"] for item in evaluators)
        full_model_routes = sum(item.routing_counts["full_model"] for item in evaluators)
        runs.append(
            PairedRun(
                seed=seed,
                full_seconds=full_seconds,
                fused_seconds=fused_seconds,
                speedup=full_seconds / fused_seconds if fused_seconds else float("inf"),
                identical_sequences=full_sequences == fused_sequences,
                maximum_energy_difference=maximum_difference,
                surrogate_routes=surrogate_routes,
                full_model_routes=full_model_routes,
            )
        )
    return PairedEvaluation(tuple(runs))
