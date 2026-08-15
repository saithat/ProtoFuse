"""Emit normalized graph, workload, and profile handoff bundles for Sai."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from protofuse.contracts import MethodologySpec, ProtoPlan

NodeKind = Literal["generator", "constraint", "optimizer", "workflow_step", "selection_gate"]


@dataclass(frozen=True)
class HandoffBundle:
    decision_id: str
    summary_md: str
    proto_plan: ProtoPlan
    graph: dict[str, Any]
    workload: dict[str, Any]
    profile: dict[str, Any]
    decision_request_md: str


def _binding_symbol(plan: ProtoPlan, extracted_name: str) -> str | None:
    for binding in plan.bindings:
        if binding.extracted_name == extracted_name:
            return binding.proto_symbol
    return None


def build_graph(
    spec: MethodologySpec,
    plan: ProtoPlan,
    *,
    scenario_id: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for index, generator in enumerate(spec.generators):
        node_id = f"gen:{index}:{_slug(generator.name)}"
        nodes.append(
            {
                "id": node_id,
                "kind": "generator",
                "label": generator.name,
                "proto_symbol": _binding_symbol(plan, generator.name),
                "output_type": generator.output,
                "traits": {"deterministic": False, "stochastic": True, "effectful": False},
                "parameters": generator.parameters,
            }
        )

    for index, constraint in enumerate(spec.constraints):
        node_id = f"cst:{index}:{_slug(constraint.name)}"
        nodes.append(
            {
                "id": node_id,
                "kind": "constraint",
                "label": constraint.name,
                "proto_symbol": _binding_symbol(plan, constraint.name),
                "metric": constraint.metric,
                "direction": constraint.direction,
                "traits": {"deterministic": True, "stochastic": False, "effectful": False},
                "parameters": constraint.parameters,
            }
        )

    for index, optimizer in enumerate(spec.optimizers):
        node_id = f"opt:{index}:{_slug(optimizer.name)}"
        nodes.append(
            {
                "id": node_id,
                "kind": "optimizer",
                "label": optimizer.name,
                "proto_symbol": _binding_symbol(plan, optimizer.name),
                "strategy": optimizer.strategy,
                "traits": {"deterministic": False, "stochastic": True, "effectful": False},
                "parameters": optimizer.parameters,
            }
        )

    generator_ids = [node["id"] for node in nodes if node["kind"] == "generator"]
    constraint_ids = [node["id"] for node in nodes if node["kind"] == "constraint"]
    optimizer_ids = [node["id"] for node in nodes if node["kind"] == "optimizer"]

    if generator_ids and constraint_ids:
        for constraint_id in constraint_ids:
            edges.append(
                {
                    "source": generator_ids[0],
                    "target": constraint_id,
                    "artifact": "candidate_sequence",
                    "role": "score_input",
                }
            )
    if constraint_ids and optimizer_ids:
        for constraint_id in constraint_ids:
            edges.append(
                {
                    "source": constraint_id,
                    "target": optimizer_ids[0],
                    "artifact": "constraint_score",
                    "role": "optimizer_feedback",
                }
            )
        edges.append(
            {
                "source": optimizer_ids[0],
                "target": generator_ids[0],
                "artifact": "accepted_proposal",
                "role": "refinement_loop",
            }
        )

    for step in spec.workflow.steps:
        step_id = f"wf:{step.id}"
        nodes.append(
            {
                "id": step_id,
                "kind": "workflow_step",
                "label": step.operation,
                "traits": {
                    "deterministic": step.id == "resolve_constraints",
                    "stochastic": step.id != "resolve_constraints",
                    "effectful": False,
                },
                "parameters": step.parameters,
            }
        )

    for edge in spec.workflow.edges:
        edges.append(
            {
                "source": f"wf:{edge.source}",
                "target": f"wf:{edge.target}",
                "artifact": edge.artifact,
                "role": "workflow",
            }
        )

    return {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "topology": plan.topology.value,
        "nodes": nodes,
        "edges": edges,
        "invariants": [
            "All hard constraints must pass before objective optimization.",
            "Windowed GC must remain within declared thresholds.",
        ],
    }


def build_workload(spec: MethodologySpec, *, scenario_id: str) -> dict[str, Any]:
    num_steps = 100
    if spec.optimizers:
        num_steps = int(spec.optimizers[0].stopping_criteria.get("num_steps", num_steps))

    segment_length = int(spec.global_parameters.get("segment_length_bp", 100))
    proposals_per_step = int(spec.global_parameters.get("proposals_per_step", 1))
    num_results = int(spec.global_parameters.get("num_results", 1))

    return {
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "fixed_inputs": {
            "segment_length_bp": segment_length,
            "constraint_parameters": {
                constraint.name: constraint.parameters for constraint in spec.constraints
            },
        },
        "varying_inputs": {
            "candidate_sequence": {"role": "mutation_delta", "count_per_step": proposals_per_step},
            "seed": {"role": "stochastic_axis"},
        },
        "reuse_axes": {
            "shared_prefix": False,
            "expected_constraint_evaluations": num_steps * proposals_per_step * num_results,
            "expected_generator_calls": num_steps * proposals_per_step * num_results,
        },
        "branches": len(spec.workflow.steps),
    }


def build_profile(spec: MethodologySpec, graph: dict[str, Any]) -> dict[str, Any]:
    num_steps = 100
    if spec.optimizers:
        num_steps = int(spec.optimizers[0].stopping_criteria.get("num_steps", num_steps))

    proposals_per_step = int(spec.global_parameters.get("proposals_per_step", 1))
    num_results = int(spec.global_parameters.get("num_results", 1))
    total_iterations = num_steps * proposals_per_step * num_results

    node_metrics: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        if node["kind"] == "constraint":
            calls = total_iterations
            duration_ms = calls * 2.0
            node_metrics.append(
                {
                    "node_id": node["id"],
                    "calls": calls,
                    "duration_ms_total": duration_ms,
                    "duration_ms_mean": 2.0,
                    "device": "local",
                    "cache_hits": 0,
                    "cache_misses": calls,
                    "quality_contribution": "high" if "GC" in node["label"] else "medium",
                    "measurement": "estimated",
                }
            )
        elif node["kind"] == "generator":
            calls = total_iterations
            node_metrics.append(
                {
                    "node_id": node["id"],
                    "calls": calls,
                    "duration_ms_total": calls * 0.02,
                    "duration_ms_mean": 0.02,
                    "device": "local",
                    "cache_hits": 0,
                    "cache_misses": calls,
                    "quality_contribution": "medium",
                    "measurement": "estimated",
                }
            )
        elif node["kind"] == "optimizer":
            node_metrics.append(
                {
                    "node_id": node["id"],
                    "calls": num_steps,
                    "duration_ms_total": num_steps * 1.5,
                    "duration_ms_mean": 1.5,
                    "device": "local",
                    "cache_hits": 0,
                    "cache_misses": num_steps,
                    "quality_contribution": "orchestration",
                    "measurement": "estimated",
                }
            )

    return {
        "schema_version": "1.0",
        "device": "local",
        "seed": 0,
        "nodes": node_metrics,
        "headline_bottleneck_node_id": _headline_bottleneck(node_metrics),
    }


def build_handoff_bundle(
    spec: MethodologySpec,
    plan: ProtoPlan,
    *,
    scenario_id: str,
    decision_id: str,
) -> HandoffBundle:
    graph = build_graph(spec, plan, scenario_id=scenario_id)
    workload = build_workload(spec, scenario_id=scenario_id)
    profile = build_profile(spec, graph)

    summary = (
        f"# Handoff: {spec.paper.title}\n\n"
        f"- Scenario: `{scenario_id}`\n"
        f"- Topology: `{plan.topology.value}`\n"
        f"- Device: `{plan.device}`\n"
        f"- Executable plan: `{plan.executable}`\n"
        f"- Headline bottleneck: `{profile['headline_bottleneck_node_id']}`\n"
    )
    decision_request = (
        f"# Decision request: {decision_id}\n\n"
        "Target: reduce amortized constraint scoring cost in the MCMC refinement loop.\n\n"
        "Allowed levers: exact prepared-state caching for repeated constraint evaluation.\n\n"
        "Quality floor: preserve windowed GC and pattern filter invariants.\n\n"
        "Budget: local CPU baseline; no Modal required for v1.\n"
    )
    return HandoffBundle(
        decision_id=decision_id,
        summary_md=summary,
        proto_plan=plan,
        graph=graph,
        workload=workload,
        profile=profile,
        decision_request_md=decision_request,
    )


def write_handoff_bundle(bundle: HandoffBundle, root: Path) -> Path:
    out_dir = root / "phillip_to_sai" / bundle.decision_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text(bundle.summary_md)
    (out_dir / "proto_plan.json").write_text(bundle.proto_plan.model_dump_json(indent=2) + "\n")
    (out_dir / "graph.json").write_text(json.dumps(bundle.graph, indent=2) + "\n")
    (out_dir / "workload.json").write_text(json.dumps(bundle.workload, indent=2) + "\n")
    (out_dir / "profile.json").write_text(json.dumps(bundle.profile, indent=2) + "\n")
    (out_dir / "decision_request.md").write_text(bundle.decision_request_md)
    return out_dir


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_")


def _headline_bottleneck(node_metrics: list[dict[str, Any]]) -> str:
    if not node_metrics:
        return "unknown"
    return max(node_metrics, key=lambda item: item["duration_ms_total"])["node_id"]
