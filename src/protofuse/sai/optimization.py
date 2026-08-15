"""Analyze Phillip handoff bundles and propose ProtoStage optimizations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OptimizationProposal:
    decision_id: str
    summary_md: str
    prepared_module_plan: dict[str, Any]
    graph_patch: dict[str, Any]
    benchmark_plan: dict[str, Any]
    decision_record_md: str


def load_handoff_bundle(root: Path, decision_id: str) -> dict[str, Any]:
    bundle_dir = root / "phillip_to_sai" / decision_id
    return {
        "summary_md": (bundle_dir / "summary.md").read_text(),
        "graph": json.loads((bundle_dir / "graph.json").read_text()),
        "workload": json.loads((bundle_dir / "workload.json").read_text()),
        "profile": json.loads((bundle_dir / "profile.json").read_text()),
        "decision_request_md": (bundle_dir / "decision_request.md").read_text(),
    }


def rank_hot_paths(profile: dict[str, Any], workload: dict[str, Any]) -> list[dict[str, Any]]:
    reuse = workload.get("reuse_axes", {})
    expected_evals = int(reuse.get("expected_constraint_evaluations", 1))

    ranked: list[dict[str, Any]] = []
    for node in profile.get("nodes", []):
        amortized = node["duration_ms_total"] * max(expected_evals / max(node["calls"], 1), 1)
        ranked.append(
            {
                "node_id": node["node_id"],
                "duration_ms_total": node["duration_ms_total"],
                "calls": node["calls"],
                "amortized_avoidable_work_ms": amortized,
                "quality_contribution": node.get("quality_contribution", "unknown"),
            }
        )
    return sorted(ranked, key=lambda item: item["amortized_avoidable_work_ms"], reverse=True)


def propose_protocstage_optimization(
    bundle: dict[str, Any],
    *,
    decision_id: str,
) -> OptimizationProposal:
    hot_paths = rank_hot_paths(bundle["profile"], bundle["workload"])
    target_node_id = hot_paths[0]["node_id"] if hot_paths else "unknown"

    prepared_module_plan = {
        "schema_version": "1.0",
        "decision_id": decision_id,
        "target_node_id": target_node_id,
        "binding_time_split": {
            "fixed_context": ["segment_length_bp", "constraint_parameters"],
            "varying_context": ["candidate_sequence", "seed"],
        },
        "prepared_state": {
            "cache_key": ["constraint_parameters", "segment_length_bp"],
            "invalidates_on": ["constraint_parameters", "segment_length_bp"],
            "resume_operation": "incremental_constraint_rescore",
        },
        "residual_graph": {
            "description": (
                "MCMC loop reuses prepared constraint context across proposals "
                "with identical fixed parameters."
            ),
            "protected_invariants": bundle["graph"].get("invariants", []),
        },
        "exactness": "exact_for_fixed_parameters",
        "fallback": "baseline_constraint_rescore",
    }

    graph_patch = {
        "schema_version": "1.0",
        "decision_id": decision_id,
        "changes": [
            {
                "operation": "insert_prepared_module",
                "before_node_id": target_node_id,
                "new_node_id": f"stage:prepared:{target_node_id}",
                "expected_benefit_ms_per_iteration": 0.03,
                "semantic_risk": "low",
                "rollback": "remove_prepared_module",
            }
        ],
    }

    benchmark_plan = {
        "schema_version": "1.0",
        "decision_id": decision_id,
        "baseline": "phillip_to_sai baseline profile",
        "candidate": "prepared-state patched graph",
        "device": bundle["profile"].get("device", "local"),
        "seed": bundle["profile"].get("seed", 0),
        "repetitions": 3,
        "metrics": [
            {"name": "total_wall_time_ms", "pass_threshold_ratio": 0.85},
            {"name": "constraint_evaluations", "pass_threshold_ratio": 1.0},
            {"name": "scientific_invariants", "pass_threshold": "all_pass"},
        ],
    }

    summary = (
        f"# ProtoStage proposal: {decision_id}\n\n"
        f"- Selected hot path: `{target_node_id}`\n"
        f"- Recommended mode: exact prepared-state constraint rescoring\n"
        f"- Expected benefit: reuse fixed GC/window parameters across MCMC proposals\n"
    )
    decision_record = (
        f"# Decision record: {decision_id}\n\n"
        "Status: **accepted** (Check-in 0 methodology approved; benchmark gate pending).\n\n"
        f"Primary optimization target: `{target_node_id}`.\n"
    )

    return OptimizationProposal(
        decision_id=decision_id,
        summary_md=summary,
        prepared_module_plan=prepared_module_plan,
        graph_patch=graph_patch,
        benchmark_plan=benchmark_plan,
        decision_record_md=decision_record,
    )


def write_optimization_proposal(proposal: OptimizationProposal, root: Path) -> Path:
    out_dir = root / "sai_to_phillip" / proposal.decision_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text(proposal.summary_md)
    (out_dir / "prepared_module_plan.json").write_text(
        json.dumps(proposal.prepared_module_plan, indent=2) + "\n"
    )
    (out_dir / "graph_patch.json").write_text(json.dumps(proposal.graph_patch, indent=2) + "\n")
    (out_dir / "benchmark_plan.json").write_text(
        json.dumps(proposal.benchmark_plan, indent=2) + "\n"
    )
    (out_dir / "decision_record.md").write_text(proposal.decision_record_md)
    return out_dir
