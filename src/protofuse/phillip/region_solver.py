"""Region-local solver orchestration matching DNA Chisel's two-step algorithm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from proto_language.core import Program

ConstraintScoreFn = Callable[[Program], float]
ProgramRunDevice = Literal["modal"] | None


@dataclass(frozen=True)
class RegionSolverConfig:
    max_region_passes: int = 5
    steps_per_region: int = 200
    convergence_violations: int = 0
    min_region_passes: int = 1
    inner_refinement_steps: int = 0
    max_windows_per_pass: int = 5
    min_inner_refinements_per_pass: int = 0
    window_bp: int = 100


@dataclass(frozen=True)
class RegionSolverResult:
    wall_time_ms: float
    region_passes: int
    final_violations: int
    program: Program
    inner_refinements: int


def run_region_local_program(
    build_program: Callable[..., Program],
    *,
    config: RegionSolverConfig,
    score_program: ConstraintScoreFn | None = None,
    run_device: ProgramRunDevice = None,
) -> RegionSolverResult:
    """Run MCMC passes with optional per-window inner refinement."""

    start = perf_counter()
    region_passes = 0
    final_violations = 0
    inner_refinements = 0
    program: Program | None = None
    score_program = score_program or _default_score_program

    for region_pass in range(config.max_region_passes):
        program = build_program(region_pass=region_pass)
        program.run(device=run_device)
        region_passes = region_pass + 1

        if config.inner_refinement_steps > 0:
            refinements_this_pass = 0
            for window_index in range(config.max_windows_per_pass):
                worst_score = score_program(program)
                if worst_score <= 0.0 and refinements_this_pass >= config.min_inner_refinements_per_pass:
                    break
                program = build_program(
                    region_pass=region_pass,
                    inner_refinement=window_index + 1,
                )
                _set_optimizer_steps(program, config.inner_refinement_steps)
                program.run(device=run_device)
                inner_refinements += 1
                refinements_this_pass += 1

        final_violations = _count_violations(program)
        if (
            region_passes >= config.min_region_passes
            and final_violations <= config.convergence_violations
        ):
            break

    if program is None:
        raise RuntimeError("region solver did not execute any passes")

    wall_time_ms = (perf_counter() - start) * 1000
    return RegionSolverResult(
        wall_time_ms=wall_time_ms,
        region_passes=region_passes,
        final_violations=final_violations,
        program=program,
        inner_refinements=inner_refinements,
    )


def _set_optimizer_steps(program: Program, num_steps: int) -> None:
    for optimizer in program.optimizers:
        optimizer.config.num_steps = num_steps


def _default_score_program(program: Program) -> float:
    if not program.constructs:
        return 0.0
    best = program.constructs[0].joined_sequences[0]
    segments = best.metadata.get("segments", {})
    scores: list[float] = []
    for segment_data in segments.values():
        for data in segment_data.get("constraints", {}).values():
            if isinstance(data, dict):
                score = data.get("score")
                if isinstance(score, (int, float)):
                    scores.append(float(score))
    return max(scores) if scores else 0.0


def _count_violations(program: Program) -> int:
    if not program.constructs:
        return 0
    best = program.constructs[0].joined_sequences[0]
    segments = best.metadata.get("segments", {})
    violations = 0
    for segment_data in segments.values():
        for data in segment_data.get("constraints", {}).values():
            if isinstance(data, dict):
                score = data.get("score")
                if isinstance(score, (int, float)) and score > 0.0:
                    violations += 1
    return violations
