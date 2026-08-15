"""Compile an extracted methodology into a reviewed Proto plan."""

from __future__ import annotations

from collections.abc import Mapping

from protofuse.contracts import (
    ComponentBinding,
    ExecutionDevice,
    MethodologySpec,
    ProtoPlan,
    TopologyRecommendation,
)


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
