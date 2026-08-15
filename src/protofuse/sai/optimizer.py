"""Apply every compatible registered fusion while preserving safe fallback."""

from __future__ import annotations

from dataclasses import dataclass

from protofuse.sai.registry import FusionRegistry


@dataclass(frozen=True)
class OptimizationResult[ProgramT]:
    program: ProgramT
    applied_fusions: tuple[str, ...]
    diagnostics: tuple[str, ...]


def optimize_program[ProgramT](
    program: ProgramT,
    registry: FusionRegistry[ProgramT],
) -> OptimizationResult[ProgramT]:
    """Return the original program for every unmatched or failed fusion."""

    current = program
    applied: list[str] = []
    diagnostics: list[str] = []
    for bundle in registry.bundles:
        try:
            compatible = bundle.matches(current)
        except Exception as error:
            diagnostics.append(f"match_failed:{bundle.qualified_id}:{type(error).__name__}")
            continue
        if not compatible:
            continue
        try:
            current = bundle.apply(current)
        except Exception as error:
            diagnostics.append(f"apply_failed:{bundle.qualified_id}:{type(error).__name__}")
            continue
        applied.append(bundle.qualified_id)
    if not applied and not diagnostics:
        diagnostics.append("no_compatible_fusion")
    return OptimizationResult(current, tuple(applied), tuple(diagnostics))
