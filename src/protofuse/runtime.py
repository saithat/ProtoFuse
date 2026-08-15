"""Public runtime entry point for transparent learned fusion."""

from __future__ import annotations

from typing import Any, cast

from protofuse.sai.optimizer import OptimizationResult, optimize_program
from protofuse.sai.registry import FusionBundle, FusionRegistry

_DEFAULT_REGISTRY: FusionRegistry[Any] = FusionRegistry()


def register_fusion(bundle: FusionBundle[Any]) -> None:
    """Register a reviewed fusion for automatic matching."""

    _DEFAULT_REGISTRY.register(bundle)


def optimize_with_report[ProgramT](
    program: ProgramT,
    *,
    registry: FusionRegistry[ProgramT] | None = None,
) -> OptimizationResult[ProgramT]:
    """Apply compatible fusions; unmatched or failed bundles leave the program intact."""

    selected = (
        registry
        if registry is not None
        else cast(FusionRegistry[ProgramT], _DEFAULT_REGISTRY)
    )
    return optimize_program(program, selected)


def optimize[ProgramT](
    program: ProgramT,
    *,
    registry: FusionRegistry[ProgramT] | None = None,
) -> ProgramT:
    """Return a transparently optimized program or the original program."""

    return optimize_with_report(program, registry=registry).program
