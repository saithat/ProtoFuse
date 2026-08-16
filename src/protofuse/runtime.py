"""Public runtime entry point for transparent learned fusion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from protofuse.sai.optimizer import OptimizationResult, optimize_program
from protofuse.sai.registry import FusionBundle, FusionRegistry

_DEFAULT_REGISTRY: FusionRegistry[Any] = FusionRegistry()
_DISCOVERY_ATTEMPTED = False
_DISCOVERY_DIAGNOSTICS: list[str] = []


def _default_bundle_root() -> Path:
    configured = os.environ.get("PROTOFUSE_BUNDLE_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "models"


def discover_fusions(
    directory: Path | None = None,
    *,
    strict: bool = True,
) -> tuple[str, ...]:
    """Load reviewed bundle artifacts into the default registry."""

    from protofuse.sai.artifacts import bundle_from_artifact, load_fusion_artifact

    root = (directory or _default_bundle_root()).resolve()
    if not root.is_dir():
        return ()
    registered: list[str] = []
    errors: list[str] = []
    existing = {bundle.qualified_id for bundle in _DEFAULT_REGISTRY.bundles}
    for manifest_path in sorted(root.glob("*/manifest.json")):
        try:
            artifact = load_fusion_artifact(manifest_path.parent, require_reviewed=True)
            bundle = bundle_from_artifact(artifact)
            if bundle.qualified_id in existing:
                continue
            _DEFAULT_REGISTRY.register(bundle)
        except Exception as exc:
            errors.append(f"bundle_load_failed:{manifest_path.parent.name}:{type(exc).__name__}")
            continue
        registered.append(bundle.qualified_id)
        existing.add(bundle.qualified_id)
    if errors and strict:
        raise RuntimeError("; ".join(errors))
    for diagnostic in errors:
        if diagnostic not in _DISCOVERY_DIAGNOSTICS:
            _DISCOVERY_DIAGNOSTICS.append(diagnostic)
    return tuple(registered)


def _ensure_default_fusions() -> None:
    global _DISCOVERY_ATTEMPTED
    if _DISCOVERY_ATTEMPTED:
        return
    _DISCOVERY_ATTEMPTED = True
    discover_fusions(strict=False)


def register_fusion(bundle: FusionBundle[Any]) -> None:
    """Register a reviewed fusion for automatic matching."""

    _DEFAULT_REGISTRY.register(bundle)


def optimize_with_report[ProgramT](
    program: ProgramT,
    *,
    registry: FusionRegistry[ProgramT] | None = None,
) -> OptimizationResult[ProgramT]:
    """Apply compatible fusions; unmatched or failed bundles leave the program intact."""

    if registry is None:
        _ensure_default_fusions()
        selected = cast(FusionRegistry[ProgramT], _DEFAULT_REGISTRY)
    else:
        selected = registry
    result = optimize_program(program, selected)
    if registry is None and _DISCOVERY_DIAGNOSTICS:
        return OptimizationResult(
            result.program,
            result.applied_fusions,
            (*_DISCOVERY_DIAGNOSTICS, *result.diagnostics),
        )
    return result


def optimize[ProgramT](
    program: ProgramT,
    *,
    registry: FusionRegistry[ProgramT] | None = None,
) -> ProgramT:
    """Return a transparently optimized program or the original program."""

    return optimize_with_report(program, registry=registry).program
