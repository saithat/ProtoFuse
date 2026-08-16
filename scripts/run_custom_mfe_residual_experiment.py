"""Run the leakage-safe CUSTOM sampled-MFE residual feasibility experiment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from protofuse.sai.custom_mfe_residual import (
    ResidualDataset,
    ResidualGates,
    build_residual_dataset,
    evaluate_residual_candidate,
    experiment_metadata,
    fit_residual_candidates,
    load_custom_mfe_examples,
    load_residual_dataset,
    save_residual_dataset,
    select_development_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "data/analysis/custom-egfp-lung"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ANALYSIS_ROOT / "experiment-manifest.json",
    )
    parser.add_argument(
        "--development-dir",
        type=Path,
        default=ANALYSIS_ROOT / "development",
    )
    parser.add_argument(
        "--external-dir",
        type=Path,
        default=ANALYSIS_ROOT / "frozen-audit",
    )
    parser.add_argument(
        "--development-cache",
        type=Path,
        default=ANALYSIS_ROOT / "residual-development-features.npz",
    )
    parser.add_argument(
        "--external-cache",
        type=Path,
        default=ANALYSIS_ROOT / "residual-external-features.npz",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ANALYSIS_ROOT / "residual-experiment.json",
    )
    parser.add_argument("--workers", type=int, default=min(os.cpu_count() or 1, 8))
    parser.add_argument("--force-recompute", action="store_true")
    return parser


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def _load_manifest(path: Path) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
    manifest = json.loads(path.read_text())
    development = manifest["development"]
    split = {
        "train": tuple(development["training_groups"]),
        "calibration": tuple(development["calibration_groups"]),
        "development_audit": tuple(development["model_selection_groups"]),
        "external_audit": tuple(manifest["frozen_external_audit"]["group_ids"]),
    }
    flattened = [group for groups in split.values() for group in groups]
    if len(flattened) != len(set(flattened)):
        raise ValueError("CUSTOM residual cohort groups overlap")
    return manifest, split


def _trace_paths(directory: Path, groups: tuple[str, ...]) -> tuple[Path, ...]:
    candidates = tuple(sorted(directory.glob("*.jsonl")))
    selected = tuple(
        path for path in candidates if any(group_id in path.stem for group_id in groups)
    )
    if len(selected) != len(groups):
        raise ValueError(
            f"{directory} contains {len(selected)} matching traces for "
            f"{len(groups)} declared groups"
        )
    return selected


def _dataset(
    *,
    paths: tuple[Path, ...],
    groups: tuple[str, ...],
    cache: Path,
    workers: int,
    force_recompute: bool,
) -> ResidualDataset:
    examples, trace_hashes = load_custom_mfe_examples(paths, allowed_groups=set(groups))
    if cache.exists() and not force_recompute:
        print(f"loading feature cache {cache}", flush=True)
        return load_residual_dataset(cache, expected_trace_sha256=trace_hashes)

    last_announced = 0

    def progress(completed: int, total: int) -> None:
        nonlocal last_announced
        if completed == total or completed - last_announced >= 1000:
            print(f"features {completed}/{total}", flush=True)
            last_announced = completed

    dataset = build_residual_dataset(
        examples,
        trace_sha256=trace_hashes,
        workers=workers,
        on_progress=progress,
    )
    save_residual_dataset(cache, dataset)
    print(f"saved feature cache {cache}", flush=True)
    return dataset


def main() -> int:
    args = _parser().parse_args()
    manifest, split = _load_manifest(args.manifest)
    gates = ResidualGates()
    development_groups = (
        *split["train"],
        *split["calibration"],
        *split["development_audit"],
    )
    declaration = {
        **experiment_metadata(),
        "gates": gates.as_dict(),
        "cohorts": {key: list(value) for key, value in split.items()},
        "external_disclosure": (
            "These four pools are disjoint from residual-model development but were previously "
            "opened for the frozen sampled-window baseline; they are not a pristine confirmation."
        ),
    }
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "running_development",
        "declaration": declaration,
        "source_manifest": str(args.manifest.resolve()),
        "source_manifest_summary_sha256": manifest["initial_paired_evaluation"][
            "summary_sha256"
        ],
    }
    _write_report(args.out, report)
    print(f"wrote frozen declaration {args.out}", flush=True)

    development_paths = _trace_paths(args.development_dir, development_groups)
    development = _dataset(
        paths=development_paths,
        groups=development_groups,
        cache=args.development_cache,
        workers=args.workers,
        force_recompute=args.force_recompute,
    )
    candidates = fit_residual_candidates(
        development,
        train_groups=split["train"],
        calibration_groups=split["calibration"],
        gates=gates,
    )
    development_reports = tuple(
        evaluate_residual_candidate(
            candidate,
            development,
            groups=split["development_audit"],
            gates=gates,
        )
        for candidate in candidates
    )
    report["development"] = {
        "trace_sha256": list(development.trace_sha256),
        "samples": len(development.actual),
        "candidates": list(development_reports),
    }
    winner = select_development_candidate(candidates, development_reports)
    if winner is None:
        report["status"] = "development_rejected"
        report["selected_candidate"] = None
        report["external_audit"] = {
            "status": "not_opened",
            "reason": "no candidate passed every predeclared development gate",
        }
        _write_report(args.out, report)
        print("development rejected every residual candidate; external pools not opened")
        return 2

    selected_report = next(
        item for item in development_reports if item["family"] == winner.family
    )
    report["status"] = "candidate_frozen"
    report["selected_candidate"] = {
        "family": winner.family,
        "config": winner.config,
        "model_sha256": winner.model_sha256,
        "support_threshold": winner.support_threshold,
        "uncertainty_threshold": winner.uncertainty_threshold,
        "development_result": selected_report,
    }
    _write_report(args.out, report)
    print(
        f"froze {winner.family} candidate {winner.model_sha256}; opening external audit",
        flush=True,
    )

    external_paths = _trace_paths(args.external_dir, split["external_audit"])
    external = _dataset(
        paths=external_paths,
        groups=split["external_audit"],
        cache=args.external_cache,
        workers=args.workers,
        force_recompute=args.force_recompute,
    )
    if set(development.trace_sha256) & set(external.trace_sha256):
        raise ValueError("CUSTOM residual external trace content overlaps development")
    external_result = evaluate_residual_candidate(
        winner,
        external,
        groups=split["external_audit"],
        gates=gates,
    )
    report["external_audit"] = {
        **external_result,
        "trace_sha256": list(external.trace_sha256),
        "trace_hash_disjoint": True,
        "group_disjoint": True,
        "pristine_confirmation": False,
    }
    report["status"] = (
        "external_pass_requires_fresh_confirmation"
        if external_result["passed"]
        else "external_rejected"
    )
    _write_report(args.out, report)
    print(
        f"external status={external_result['status']} report={args.out}",
        flush=True,
    )
    return 0 if external_result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
