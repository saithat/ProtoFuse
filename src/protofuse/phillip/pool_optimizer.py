"""Pool-based propose-score-select orchestration matching CUSTOM's algorithm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from proto_language.core import Program

from protofuse.checkpoints import run_program

ProgramRunDevice = Literal["modal"] | None


@dataclass(frozen=True)
class PoolOptimizerConfig:
    n_pool: int = 500
    top_k: int = 10
    homopolymer_max: int = 7


@dataclass(frozen=True)
class PoolCandidate:
    program: Program
    composite_score: float
    tissue_score: float
    gc_score: float
    homopolymer_ok: bool


@dataclass(frozen=True)
class PoolOptimizerResult:
    wall_time_ms: float
    n_pool: int
    candidates_scored: int
    candidates_passed_filter: int
    best: PoolCandidate
    program: Program


def _max_homopolymer_run(sequence: str) -> int:
    if not sequence:
        return 0
    best = current = 1
    for index in range(1, len(sequence)):
        if sequence[index] == sequence[index - 1]:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _gc_deviation(sequence: str, *, target_gc: float) -> float:
    if not sequence:
        return 1.0
    gc = 100.0 * sum(base in "GC" for base in sequence.upper()) / len(sequence)
    return abs(gc - target_gc) / 100.0


def _extract_scores(program: Program) -> tuple[float, float]:
    if not program.constructs:
        return 0.0, 1.0
    best = program.constructs[0].joined_sequences[0]
    segments = best.metadata.get("segments", {})
    tissue_score = 0.0
    gc_score = 1.0
    for segment_data in segments.values():
        for label, data in segment_data.get("constraints", {}).items():
            if not isinstance(data, dict):
                continue
            score = data.get("score")
            if not isinstance(score, (int, float)):
                continue
            if "tissue" in label:
                metadata = data.get("metadata") or {}
                tissue_score = float(metadata.get("mean_tissue_score", 1.0 - score))
            if label in {"gc_content", "gc_target"}:
                gc_score = float(score)
    return tissue_score, gc_score


def run_pool_optimizer(
    build_program: Callable[[], Program],
    *,
    config: PoolOptimizerConfig,
    target_gc: float = 50.0,
    run_device: ProgramRunDevice = None,
) -> PoolOptimizerResult:
    """Generate a pool of MCMC candidates and return the top-scoring feasible sequence."""

    start = perf_counter()
    candidates: list[PoolCandidate] = []
    best: PoolCandidate | None = None

    for _ in range(config.n_pool):
        program = build_program()
        run_program(program, device=run_device)
        sequence = program.constructs[0].joined_sequences[0].sequence.upper()
        max_run = _max_homopolymer_run(sequence)
        homopolymer_ok = max_run < config.homopolymer_max
        tissue_score, gc_score = _extract_scores(program)
        gc_penalty = _gc_deviation(sequence, target_gc=target_gc)
        composite = tissue_score - gc_penalty - (0.5 if not homopolymer_ok else 0.0)

        candidate = PoolCandidate(
            program=program,
            composite_score=composite,
            tissue_score=tissue_score,
            gc_score=gc_score,
            homopolymer_ok=homopolymer_ok,
        )
        candidates.append(candidate)
        if best is None or candidate.composite_score > best.composite_score:
            best = candidate

    if best is None:
        raise RuntimeError("pool optimizer did not generate any candidates")

    passed = [item for item in candidates if item.homopolymer_ok]
    ranked = sorted(passed or candidates, key=lambda item: item.composite_score, reverse=True)
    selected = ranked[0]

    wall_time_ms = (perf_counter() - start) * 1000
    return PoolOptimizerResult(
        wall_time_ms=wall_time_ms,
        n_pool=config.n_pool,
        candidates_scored=len(candidates),
        candidates_passed_filter=len(passed),
        best=selected,
        program=selected.program,
    )
