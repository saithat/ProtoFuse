"""Pure aggregation for the paired experiment JSON report."""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _speedup_confidence_interval(runs: Sequence[Mapping[str, Any]]) -> list[float] | None:
    eligible = [run for run in runs if run["speedup"] is not None]
    if len(eligible) < 2:
        return None
    rng = random.Random(0)
    ratios: list[float] = []
    for _ in range(2_000):
        sample = [rng.choice(eligible) for _ in eligible]
        fused_total = sum(float(run["fused_seconds"]) for run in sample)
        ratios.append(sum(float(run["full_seconds"]) for run in sample) / fused_total)
    lower = _percentile(ratios, 0.025)
    upper = _percentile(ratios, 0.975)
    return [lower, upper] if lower is not None and upper is not None else None


def aggregate_paired_runs(
    runs: Sequence[Mapping[str, Any]],
    offline_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute every declared metric; unavailable measurements remain None."""

    successful = [run for run in runs if run["speedup"] is not None]
    speedups = [float(run["speedup"]) for run in successful]
    full_times = [float(run["full_seconds"]) for run in successful]
    fused_times = [float(run["fused_seconds"]) for run in successful]
    accuracy_runs = [run for run in runs if run["status"] == "ok"]
    differences = [
        float(value) for run in accuracy_runs for value in run["finite_energy_differences"]
    ]
    regrets = [
        float(run["best_energy_regret"])
        for run in accuracy_runs
        if run["best_energy_regret"] is not None
    ]
    sequence_agreements = [
        float(run["sequence_agreement"])
        for run in accuracy_runs
        if run["sequence_agreement"] is not None
    ]
    top_k_recalls = [
        float(run["top_k_recall"])
        for run in accuracy_runs
        if run["top_k_recall"] is not None
    ]
    availability = [
        float(run["result_availability_agreement"])
        for run in runs
        if run["result_availability_agreement"] is not None
    ]
    surrogate_routes = sum(int(run["surrogate_routes"]) for run in runs)
    parent_routes = sum(int(run["full_model_routes"]) for run in runs)
    exact_parallel_routes = sum(int(run.get("exact_parallel_routes", 0)) for run in runs)
    parallelized_parent_evaluations = sum(
        int(run.get("initial_stage_parent_item_evaluations_parallelized", 0))
        for run in runs
    )
    initial_parent_evaluations_bypassed = sum(
        int(
            run.get(
                "initial_stage_parent_item_evaluations_bypassed",
                run["parent_item_evaluations_avoided"],
            )
        )
        for run in runs
    )
    fallback_parent_evaluations = sum(
        int(run["parent_item_evaluations_from_fallback"]) for run in runs
    )
    final_validation_parent_evaluations = sum(
        int(run.get("mandatory_final_validation_parent_item_evaluations", 0))
        for run in runs
    )
    net_parent_evaluations_avoided = sum(
        int(
            run.get(
                "net_parent_item_evaluations_avoided",
                int(run["parent_item_evaluations_avoided"])
                - int(run.get("mandatory_final_validation_parent_item_evaluations", 0)),
            )
        )
        for run in runs
    )
    routed = surrogate_routes + parent_routes + exact_parallel_routes
    target_objectives = max((int(run["target_objectives"]) for run in runs), default=0)
    reason_counts: Counter[str] = Counter()
    for run in runs:
        reason_counts.update(run["routing_reasons"])
    wins = sum(regret < -1e-9 for regret in regrets)
    losses = sum(regret > 1e-9 for regret in regrets)
    ties = len(regrets) - wins - losses
    total_fused = sum(fused_times)
    status_counts = Counter(str(run["status"]) for run in runs)
    energy_comparison_reasons = sorted(
        {
            str(run["energy_comparison_reason"])
            for run in runs
            if run.get("energy_comparison_reason")
        }
    )

    report: dict[str, Any] = {
        "timing": {
            "full_total_seconds": sum(full_times),
            "fused_total_seconds": total_fused,
            "net_speedup": sum(full_times) / total_fused if total_fused > 0 else None,
            "mean_seed_speedup": sum(speedups) / len(speedups) if speedups else None,
            "median_seed_speedup": median(speedups) if speedups else None,
            "speedup_bootstrap_95_ci": _speedup_confidence_interval(runs),
            "full_p50_seconds": _percentile(full_times, 0.50),
            "full_p95_seconds": _percentile(full_times, 0.95),
            "fused_p50_seconds": _percentile(fused_times, 0.50),
            "fused_p95_seconds": _percentile(fused_times, 0.95),
            "surrogate_inference_seconds": sum(float(run["surrogate_seconds"]) for run in runs),
            "gate_seconds": sum(float(run["gate_seconds"]) for run in runs),
            "fallback_parent_seconds": sum(
                float(run["fallback_parent_seconds"]) for run in runs
            ),
            "exact_parallel_parent_seconds": sum(
                float(run.get("exact_parallel_parent_seconds", 0.0)) for run in runs
            ),
            "final_validation_seconds": None,
            "per_step_p50_seconds": None,
            "per_step_p95_seconds": None,
        },
        "accuracy": {
            "candidate_pool_hash_available_runs": sum(
                run.get("candidate_pool_identical") is not None for run in runs
            ),
            "candidate_pool_identical_runs": sum(
                run.get("candidate_pool_identical") is True for run in runs
            ),
            "energy_comparable_runs": sum(bool(run.get("energy_comparable", True)) for run in runs),
            "energy_comparison_reason": (
                "; ".join(energy_comparison_reasons) if energy_comparison_reasons else None
            ),
            "final_energy_mae": sum(differences) / len(differences) if differences else None,
            "final_energy_rmse": (
                math.sqrt(sum(value * value for value in differences) / len(differences))
                if differences
                else None
            ),
            "final_energy_max_absolute_difference": max(differences, default=None),
            "mean_best_energy_regret": sum(regrets) / len(regrets) if regrets else None,
            "median_best_energy_regret": median(regrets) if regrets else None,
            "mean_sequence_agreement": (
                sum(sequence_agreements) / len(sequence_agreements)
                if sequence_agreements
                else None
            ),
            "all_final_sequences_identical": (
                all(bool(run["identical_sequences"]) for run in accuracy_runs)
                if accuracy_runs
                else None
            ),
            "mean_top_k_recall": sum(top_k_recalls) / len(top_k_recalls) if top_k_recalls else None,
            "mean_result_availability_agreement": (
                sum(availability) / len(availability) if availability else None
            ),
            "seed_wins_ties_losses": {"fused_wins": wins, "ties": ties, "fused_losses": losses},
            "per_objective_mae": None,
            "per_objective_rmse": None,
            "per_objective_max_error": None,
            "rank_correlation": None,
            "accepted_per_objective_mae": None,
            "accepted_per_objective_max_error": None,
            "accepted_mae_q95_q05_fraction": None,
            "offline_selective_coverage": None,
            "threshold_agreement": None,
            "false_acceptance_rate": None,
            "false_rejection_rate": None,
            "selective_risk_curve": None,
            "best_seen_score_curve": None,
            "time_to_quality": None,
            "pareto_hypervolume": None,
        },
        "routing": {
            "surrogate_routes": surrogate_routes,
            "exact_parallel_routes": exact_parallel_routes,
            "full_model_routes": parent_routes,
            "surrogate_coverage": surrogate_routes / routed if routed else None,
            "exact_parallel_coverage": (
                exact_parallel_routes / routed if routed else None
            ),
            "deferral_reasons": dict(sorted(reason_counts.items())),
            "target_objective_count": target_objectives,
            "initial_stage_target_parent_item_evaluations_bypassed": (
                initial_parent_evaluations_bypassed
            ),
            "mandatory_final_validation_parent_item_evaluations": (
                final_validation_parent_evaluations
            ),
            "net_parent_item_evaluations_avoided": net_parent_evaluations_avoided,
            # Backward-compatible alias. This is an initial-stage count, not net savings.
            "target_parent_item_evaluations_avoided": initial_parent_evaluations_bypassed,
            "target_parent_item_evaluations_avoided_scope": (
                "initial routing stage only; mandatory final validation is excluded"
            ),
            "target_parent_item_evaluations_from_fallback": fallback_parent_evaluations,
            "target_parent_item_evaluations_parallelized": (
                parallelized_parent_evaluations
            ),
            "parent_item_evaluation_definition": (
                "one original constraint evaluated for one candidate; final validation counts "
                "every original constraint it executes, while initial bypasses cover only the "
                "fused target objectives"
            ),
            "deferral_recovery": None,
        },
        "work": {
            "planned_steps": None,
            "completed_steps": None,
            "proposals": routed,
            "accepted_moves": None,
            "parent_calls": None,
        },
        "resources": {
            "accelerator_seconds": None,
            "peak_memory_bytes": None,
            "retry_count": None,
            "cost": None,
        },
        "reliability": {
            "paired_runs": len(runs),
            "timing_runs": len(successful),
            "fully_valid_accuracy_runs": status_counts["ok"],
            "arm_failures": status_counts["arm_failed"],
            "candidate_pool_mismatches": status_counts["candidate_pool_mismatch"],
            "non_finite_energy_runs": status_counts["non_finite_energy"],
            "output_length_mismatches": status_counts["output_length_mismatch"],
        },
        "not_measured": [
            "Per-objective prediction error requires a separate held-out accuracy audit; "
            "shadow parent scoring is excluded from runtime runs.",
            "Proto does not currently expose accepted moves, per-step timing, accelerator use, "
            "memory, retries, or cost through Program.run().",
        ],
    }
    if offline_metrics is not None:
        accuracy = report["accuracy"]
        accuracy["per_objective_mae"] = offline_metrics.get("audit_mae")
        accuracy["per_objective_rmse"] = offline_metrics.get("audit_rmse")
        accuracy["per_objective_max_error"] = offline_metrics.get("audit_max_error")
        accuracy["rank_correlation"] = offline_metrics.get("audit_rank_correlation")
        accuracy["accepted_per_objective_mae"] = offline_metrics.get("audit_accepted_mae")
        accuracy["accepted_per_objective_max_error"] = offline_metrics.get(
            "audit_accepted_max_error"
        )
        accuracy["accepted_mae_q95_q05_fraction"] = offline_metrics.get(
            "audit_accepted_mae_q95_q05_fraction"
        )
        accuracy["offline_selective_coverage"] = offline_metrics.get(
            "audit_selective_coverage"
        )
    return report
