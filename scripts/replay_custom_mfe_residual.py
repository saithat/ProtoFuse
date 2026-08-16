"""Replay a frozen residual candidate against saved exact outputs on opened seeds."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from protofuse.sai.analyzer import load_reviewed_program
from protofuse.sai.custom_mfe_residual import (
    ResidualGates,
    build_residual_custom_mfe_bundle,
    fit_residual_candidates,
    load_residual_dataset,
)
from protofuse.sai.evaluation import _outputs, _routing_metrics, apply_program_seed

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "data/analysis/custom-egfp-lung"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment",
        type=Path,
        default=ANALYSIS_ROOT / "residual-experiment.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ANALYSIS_ROOT / "experiment-manifest.json",
    )
    parser.add_argument(
        "--development-cache",
        type=Path,
        default=ANALYSIS_ROOT / "residual-development-features.npz",
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
        "--out",
        type=Path,
        default=ANALYSIS_ROOT / "residual-opened-seed-replay.json",
    )
    return parser


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def _sequence_hashes(sequences: tuple[str, ...]) -> list[str]:
    return [hashlib.sha256(sequence.encode()).hexdigest() for sequence in sequences]


def main() -> int:
    args = _parser().parse_args()
    experiment = json.loads(args.experiment.read_text())
    if (
        experiment.get("status") != "external_pass_requires_fresh_confirmation"
        or experiment.get("external_audit", {}).get("passed") is not True
    ):
        raise ValueError("residual experiment has no passing frozen external candidate")
    manifest = json.loads(args.manifest.read_text())
    development = manifest["development"]
    train_groups = tuple(development["training_groups"])
    calibration_groups = tuple(development["calibration_groups"])
    trace_hashes = tuple(experiment["development"]["trace_sha256"])
    dataset = load_residual_dataset(
        args.development_cache,
        expected_trace_sha256=trace_hashes,
    )
    candidates = fit_residual_candidates(
        dataset,
        train_groups=train_groups,
        calibration_groups=calibration_groups,
        gates=ResidualGates(),
    )
    selected = experiment["selected_candidate"]
    candidate = next(item for item in candidates if item.family == selected["family"])
    if candidate.model_sha256 != selected["model_sha256"]:
        raise ValueError("refitted residual model does not match the frozen model hash")

    reference = load_reviewed_program(args.collection, program_id=args.program_id)
    bundle = build_residual_custom_mfe_bundle(
        reference.program,
        candidate=candidate,
        workers=args.workers,
    )
    baseline_report = json.loads(args.baseline_report.read_text())
    if baseline_report.get("provenance", {}).get("program_source_sha256") != reference.entry.sha256:
        raise ValueError("saved exact outputs came from a different program source")

    baseline_by_seed = {int(run["seed"]): run for run in baseline_report["runs"]}
    seeds = tuple(sorted(baseline_by_seed))
    warmup_seed = max(seeds) + 1
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
            "kind": "opened-seed fused-only replay",
            "full_outputs": str(args.baseline_report.resolve()),
            "timing_claim": (
                "Residual arm timings are new; saved full-arm timings are historical and "
                "must not be presented as a new counterbalanced paired benchmark."
            ),
            "confirmation": False,
        },
        "candidate": {
            "family": candidate.family,
            "model_sha256": candidate.model_sha256,
            "bundle": bundle.qualified_id,
            "external_report": str(args.experiment.resolve()),
        },
        "warmup": {"seed": warmup_seed, "residual_seconds": warmup_seconds},
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
        fused.run()
        residual_seconds = perf_counter() - started
        outputs = _outputs(fused, optimizer_index=0)
        routing = _routing_metrics(fused)
        full_sequences = tuple(saved["full_sequences"])
        intersection = len(set(full_sequences) & set(outputs.sequences))
        recall = intersection / len(set(full_sequences))
        positional_agreement = sum(
            left == right
            for left, right in zip(full_sequences, outputs.sequences, strict=False)
        ) / max(len(full_sequences), len(outputs.sequences))
        pool_identical = (
            outputs.candidate_pool_sha256 == saved["full_candidate_pool_sha256"]
            and outputs.candidate_pool_size == saved["full_candidate_pool_size"]
        )
        run = {
            "seed": seed,
            "status": "ok" if pool_identical else "candidate_pool_mismatch",
            "candidate_pool_identical": pool_identical,
            "full_candidate_pool_sha256": saved["full_candidate_pool_sha256"],
            "residual_candidate_pool_sha256": outputs.candidate_pool_sha256,
            "top10_recall": recall,
            "positional_agreement": positional_agreement,
            "ordered_identical": full_sequences == outputs.sequences,
            "full_sequence_sha256": _sequence_hashes(full_sequences),
            "residual_sequence_sha256": _sequence_hashes(outputs.sequences),
            "original_sampled_top10_recall": saved["top_k_recall"],
            "top10_recall_delta_vs_original_sampled": recall - saved["top_k_recall"],
            "historical_full_seconds": saved["full_seconds"],
            "original_sampled_seconds": saved["fused_seconds"],
            "residual_seconds": residual_seconds,
            "routing": routing,
        }
        payload["runs"].append(run)
        _write(args.out, payload)
        print(
            f"seed {seed} ({index}/{len(seeds)}): recall={recall:.2f} "
            f"original={saved['top_k_recall']:.2f} seconds={residual_seconds:.2f}",
            flush=True,
        )

    runs = payload["runs"]
    recalls = np.asarray([run["top10_recall"] for run in runs], dtype=np.float64)
    original_recalls = np.asarray(
        [run["original_sampled_top10_recall"] for run in runs], dtype=np.float64
    )
    residual_total = sum(run["residual_seconds"] for run in runs)
    historical_full_total = sum(run["historical_full_seconds"] for run in runs)
    routes: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for run in runs:
        routes["surrogate"] += run["routing"]["surrogate_routes"]
        routes["full_model"] += run["routing"]["full_model_routes"]
        reasons.update(run["routing"]["routing_reasons"])
    pool_matches = sum(run["candidate_pool_identical"] for run in runs)
    gates = {
        "all_candidate_pools_identical": pool_matches == len(runs),
        "mean_top10_recall": float(recalls.mean()) >= 0.80,
        "minimum_top10_recall": float(recalls.min()) >= 0.60,
        "no_execution_failures": all(run["status"] == "ok" for run in runs),
    }
    payload["summary"] = {
        "runs": len(runs),
        "candidate_pool_matches": pool_matches,
        "mean_top10_recall": float(recalls.mean()),
        "minimum_top10_recall": float(recalls.min()),
        "ordered_identical_runs": sum(run["ordered_identical"] for run in runs),
        "mean_original_sampled_top10_recall": float(original_recalls.mean()),
        "mean_top10_recall_delta_vs_original_sampled": float(
            (recalls - original_recalls).mean()
        ),
        "residual_total_seconds": residual_total,
        "historical_full_total_seconds": historical_full_total,
        "historical_nonpaired_speedup_estimate": historical_full_total / residual_total,
        "surrogate_routes": routes["surrogate"],
        "full_model_routes": routes["full_model"],
        "surrogate_coverage": routes["surrogate"] / sum(routes.values()),
        "routing_reasons": dict(reasons),
        "gates": gates,
    }
    payload["status"] = (
        "opened_seed_replay_pass_requires_fresh_paired_confirmation"
        if all(gates.values())
        else "opened_seed_replay_fail"
    )
    _write(args.out, payload)
    print(f"status={payload['status']} report={args.out}")
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
