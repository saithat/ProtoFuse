"""End-to-end orchestration over shared, replaceable components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from protofuse.phillip.compiler import compile_proto_plan
from protofuse.phillip.contracts import (
    ExecutionDevice,
    MethodologySpec,
    ProtoPlan,
    TopologyRecommendation,
)
from protofuse.phillip.extractor import ScientificAgent
from protofuse.phillip.topology import recommend_topologies


@dataclass(frozen=True)
class PipelineResult:
    methodology: MethodologySpec
    recommendations: tuple[TopologyRecommendation, ...]
    plan: ProtoPlan


def run_pipeline(
    paper_text: str,
    agent: ScientificAgent,
    *,
    registry: Mapping[str, str] | None = None,
    device: ExecutionDevice = "local",
) -> PipelineResult:
    methodology = agent.extract(paper_text)
    recommendations = tuple(recommend_topologies(methodology))
    if not recommendations:
        raise ValueError("no compatible workflow topology was found")
    plan = compile_proto_plan(
        methodology,
        recommendations[0],
        registry=registry,
        device=device,
    )
    return PipelineResult(methodology, recommendations, plan)
