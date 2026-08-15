"""Compile an extracted methodology into a reviewed Proto plan."""

from __future__ import annotations

from collections.abc import Mapping

from protofuse.phillip.contracts import (
    ComponentBinding,
    ExecutionDevice,
    MethodologySpec,
    ProtoPlan,
    TopologyRecommendation,
)


class UnresolvedBindingsError(ValueError):
    """Raised when source generation is requested before every binding is resolved."""

    def __init__(self, unresolved: list[str]) -> None:
        self.unresolved = unresolved
        super().__init__(f"unresolved component bindings: {', '.join(unresolved)}")


def require_resolved_plan(plan: ProtoPlan) -> ProtoPlan:
    """Refuse downstream generation until the compiled plan is executable."""

    unresolved = [item.extracted_name for item in plan.bindings if item.status != "bound"]
    if not plan.executable or unresolved or plan.unresolved:
        raise UnresolvedBindingsError(plan.unresolved or unresolved)
    return plan


def compile_proto_plan(
    spec: MethodologySpec,
    recommendation: TopologyRecommendation,
    *,
    registry: Mapping[str, str] | None = None,
    device: ExecutionDevice = "local",
) -> ProtoPlan:
    """Bind paper component names only through an explicit reviewed registry."""

    approved = registry or {}
    names = [
        *(item.name for item in spec.generators),
        *(item.name for item in spec.constraints),
        *(item.name for item in spec.optimizers),
    ]
    bindings = [
        ComponentBinding(
            extracted_name=name,
            proto_symbol=approved.get(name),
            status="bound" if name in approved else "unresolved",
        )
        for name in names
    ]
    unresolved = [item.extracted_name for item in bindings if item.status == "unresolved"]
    return ProtoPlan(
        paper=spec.paper,
        topology=recommendation.topology,
        device=device,
        bindings=bindings,
        workflow=spec.workflow,
        executable=not unresolved,
        unresolved=unresolved,
    )
