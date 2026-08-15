"""End-to-end orchestration over shared, replaceable components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from protofuse.contracts import (
    ExecutionDevice,
    MethodologySpec,
    ProtoPlan,
    TopologyRecommendation,
)
from protofuse.integration import compile_proto_plan
from protofuse.sai import recommend_topologies
from protofuse.scientific_agent import ScientificAgent


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
