"""Run the frozen adaptive CUSTOM boundary against saved opened-seed outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import numpy as np

from protofuse.sai.analyzer import load_reviewed_program
from protofuse.sai.custom_mfe_boundary import build_adaptive_custom_mfe_bundle
from protofuse.sai.evaluation import _outputs, _routing_metrics, apply_program_seed

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "data/analysis/custom-egfp-lung"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment",
        type=Path,
        default=ANALYSIS_ROOT / "adaptive-boundary-experiment.json",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=ANALYSIS_ROOT / "paired-sampled-window.json",
    )
    parser.add_argument(
        "--collection",
        type=Path,
        default=REPO_ROOT / "proto_programs/generated/custom-egfp-lung",
    )
    parser.add_argument("--program-id", default="design-001")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--boundary-budget",
        type=int,
        help="Exploratory override of the frozen development-selected boundary.",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="*",
        help="Optional subset of saved opened seeds; defaults to every saved seed.",
    )
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument(
        "--out",
        type=Path,
        default=ANALYSIS_ROOT / "adaptive-boundary-opened-seed-replay.json",
    )
    return parser


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def _sequence_hashes(sequences: tuple[str, ...]) -> list[str]:
    return [hashlib.sha256(sequence.encode()).hexdigest() for sequence in sequences]


def _selected_mfe_routes(program: Any) -> tuple[str | None, ...]:
    optimizer = program.optimizers[0]
    return tuple(
        sequence._constraints_metadata["custom_mfe"]["data"].get("protofuse_route")
        for sequence in optimizer.segments[0].result_sequences
    )


def main() -> int:
    args = _parser().parse_args()
    experiment = json.loads(args.experiment.read_text())
    selected = experiment.get("selected_policy") or {}
    if (
        experiment.get("status")
        != "external_pass_requires_runtime_and_fresh_confirmation"
        or experiment.get("external_audit", {}).get("passed") is not True
        or selected.get("source") != "sampled"
    ):
        raise ValueError("adaptive experiment has no frozen sampled boundary policy")
    frozen_boundary_budget = int(selected["boundary_budget"])
    boundary_budget = args.boundary_budget or frozen_boundary_budget
    mfe_tail_budget = int(
        selected.get(
            "mfe_tail_budget",
            int(bool(selected.get("exact_mfe_extrema_closure", False))),
        )
    )

    reference = load_reviewed_program(args.collection, program_id=args.program_id)
    bundle = build_adaptive_custom_mfe_bundle(
        reference.program,
        workers=args.workers,
        boundary_budget=boundary_budget,
        mfe_tail_budget=mfe_tail_budget,
    )
    baseline_report = json.loads(args.baseline_report.read_text())
    if (
        baseline_report.get("provenance", {}).get("program_source_sha256")
        != reference.entry.sha256
    ):
        raise ValueError("saved exact outputs came from a different program source")

    baseline_by_seed = {int(run["seed"]): run for run in baseline_report["runs"]}
    seeds = tuple(args.seeds) if args.seeds else tuple(sorted(baseline_by_seed))
    missing = sorted(set(seeds) - set(baseline_by_seed))
    if missing:
        raise ValueError(f"saved baseline is missing requested seeds: {missing}")
    if len(set(seeds)) != len(seeds):
        raise ValueError("adaptive replay seeds must be unique")

    warmup_seed = max(baseline_by_seed) + 1
    warmup_seconds: float | None = None
    if not args.skip_warmup:
        warmup = bundle.apply(
            load_reviewed_program(args.collection, program_id=args.program_id).program
        )
        apply_program_seed(warmup, warmup_seed)
        warmup_started = perf_counter()
        warmup.run()
        warmup_seconds = perf_counter() - warmup_started

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "running",
        "protocol": {
            "kind": "opened-seed adaptive fused-only replay",
            "policy_source": str(args.experiment.resolve()),
            "full_outputs": str(args.baseline_report.resolve()),
            "timing_claim": (
                "Adaptive timings are new; saved full-arm timings are historical and "
                "must not be presented as a new counterbalanced paired benchmark."
            ),
            "confirmation": False,
            "policy_selection": (
                "frozen_development_policy"
                if boundary_budget == frozen_boundary_budget
                else "posthoc_exploratory_boundary_override"
            ),
            "selected_candidates": (
                "Every returned candidate is exactly rescored for MFE before selection "
                "finishes; top-10 identity remains an empirical task-level result."
            ),
        },
        "policy": {
            "bundle": bundle.qualified_id,
            "source": selected["source"],
            "boundary_budget": boundary_budget,
            "exact_mfe_extrema_closure": mfe_tail_budget > 0,
            "mfe_tail_budget": mfe_tail_budget,
            "development_report": str(args.experiment.resolve()),
        },
        "warmup": {
            "seed": warmup_seed if not args.skip_warmup else None,
            "adaptive_seconds": warmup_seconds,
        },
        "runs": [],
    }
    _write(args.out, payload)

    for index, seed in enumerate(seeds, start=1):
        saved = baseline_by_seed[seed]
        fused = bundle.apply(
            load_reviewed_program(args.collection, program_id=args.program_id).program
        )
        apply_program_seed(fused, seed)
        started = perf_counter()
        try:
            fused.run()
            adaptive_seconds = perf_counter() - started
            outputs = _outputs(fused, optimizer_index=0)
            routing = _routing_metrics(fused)
            evaluator = cast(Any, fused)._protofuse_evaluators[0]
            boundary_report = evaluator.boundary_reports[-1]
            selected_routes = _selected_mfe_routes(fused)
            full_sequences = tuple(saved["full_sequences"])
            optimizer = fused.optimizers[0]
            proposal_index_by_sequence = {
                proposal.sequence: proposal_index
                for proposal_index, proposal in enumerate(
                    optimizer.segments[0].proposal_sequences
                )
            }
            initial_rank_by_index = {
                proposal_index: rank
                for rank, proposal_index in enumerate(
                    evaluator.last_initial_ranking,
                    start=1,
                )
            }
            exact_top10_initial_ranks = [
                initial_rank_by_index[proposal_index_by_sequence[sequence]]
                for sequence in full_sequences
            ]
            intersection = len(set(full_sequences) & set(outputs.sequences))
            recall = intersection / len(set(full_sequences))
            positional_agreement = sum(
                left == right
                for left, right in zip(
                    full_sequences,
                    outputs.sequences,
                    strict=False,
                )
            ) / max(len(full_sequences), len(outputs.sequences))
            pool_identical = (
                outputs.candidate_pool_sha256 == saved["full_candidate_pool_sha256"]
                and outputs.candidate_pool_size == saved["full_candidate_pool_size"]
            )
            all_selected_exact = (
                boundary_report["all_selected_exact"] is True
                and len(selected_routes) == len(outputs.sequences)
                and all(route == "full_model" for route in selected_routes)
            )
            status = (
                "ok"
                if pool_identical and all_selected_exact
                else "runtime_invariant_failed"
            )
            run = {
                "seed": seed,
                "status": status,
                "error_type": None,
                "candidate_pool_identical": pool_identical,
                "full_candidate_pool_sha256": saved["full_candidate_pool_sha256"],
                "adaptive_candidate_pool_sha256": outputs.candidate_pool_sha256,
                "top10_recall": recall,
                "positional_agreement": positional_agreement,
                "ordered_identical": full_sequences == outputs.sequences,
                "full_sequence_sha256": _sequence_hashes(full_sequences),
                "adaptive_sequence_sha256": _sequence_hashes(outputs.sequences),
                "all_selected_mfe_exact": all_selected_exact,
                "selected_mfe_routes": selected_routes,
                "exact_top10_initial_ranks": exact_top10_initial_ranks,
                "maximum_exact_top10_initial_rank": max(exact_top10_initial_ranks),
                "boundary": boundary_report,
                "original_sampled_top10_recall": saved["top_k_recall"],
                "top10_recall_delta_vs_original_sampled": (
                    recall - saved["top_k_recall"]
                ),
                "historical_full_seconds": saved["full_seconds"],
                "original_sampled_seconds": saved["fused_seconds"],
                "adaptive_seconds": adaptive_seconds,
                "routing": routing,
            }
        except Exception as error:  # noqa: BLE001 - preserve partial experiment
            adaptive_seconds = perf_counter() - started
            run = {
                "seed": seed,
                "status": "execution_failed",
                "error_type": type(error).__name__,
                "adaptive_seconds": adaptive_seconds,
                "historical_full_seconds": saved["full_seconds"],
                "original_sampled_seconds": saved["fused_seconds"],
            }
        payload["runs"].append(run)
        _write(args.out, payload)
        recall_text = (
            f"{run['top10_recall']:.2f}" if "top10_recall" in run else "n/a"
        )
        print(
            f"seed {seed} ({index}/{len(seeds)}): status={run['status']} "
            f"recall={recall_text} seconds={adaptive_seconds:.2f}",
            flush=True,
        )

    runs = payload["runs"]
    successful = [run for run in runs if run["status"] == "ok"]
    recalls = np.asarray(
        [run["top10_recall"] for run in successful],
        dtype=np.float64,
    )
    adaptive_total = sum(float(run["adaptive_seconds"]) for run in runs)
    historical_full_total = sum(float(run["historical_full_seconds"]) for run in runs)
    routes: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for run in successful:
        routes["surrogate"] += run["routing"]["surrogate_routes"]
        routes["full_model"] += run["routing"]["full_model_routes"]
        reasons.update(run["routing"]["routing_reasons"])
    gates = {
        "all_candidate_pools_identical": all(
            run.get("candidate_pool_identical") is True for run in runs
        ),
        "mean_top10_recall": len(recalls) == len(runs)
        and float(recalls.mean()) >= 1.0,
        "minimum_top10_recall": len(recalls) == len(runs)
        and float(recalls.min()) >= 1.0,
        "all_selected_mfe_exact": all(
            run.get("all_selected_mfe_exact") is True for run in runs
        ),
        "no_execution_failures": len(successful) == len(runs),
        "no_whole_pool_adaptive_fallbacks": all(
            run.get("boundary", {}).get("status") == "adaptive" for run in runs
        ),
    }
    payload["summary"] = {
        "runs": len(runs),
        "successful_runs": len(successful),
        "mean_top10_recall": float(recalls.mean()) if len(recalls) else None,
        "minimum_top10_recall": float(recalls.min()) if len(recalls) else None,
        "ordered_identical_runs": sum(
            bool(run.get("ordered_identical")) for run in runs
        ),
        "adaptive_total_seconds": adaptive_total,
        "historical_full_total_seconds": historical_full_total,
        "historical_nonpaired_speedup_estimate": (
            historical_full_total / adaptive_total if adaptive_total > 0.0 else None
        ),
        "surrogate_routes": routes["surrogate"],
        "full_model_routes": routes["full_model"],
        "surrogate_coverage": (
            routes["surrogate"] / sum(routes.values()) if routes else None
        ),
        "routing_reasons": dict(sorted(reasons.items())),
        "gates": gates,
    }
    payload["status"] = (
        "opened_seed_runtime_pass_requires_fresh_paired_confirmation"
        if all(gates.values())
        else "opened_seed_runtime_fail"
    )
    _write(args.out, payload)
    print(f"status={payload['status']} report={args.out}")
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
