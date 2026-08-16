"""Select and externally test an adaptive exact-rescoring boundary for CUSTOM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from protofuse.sai.custom_mfe_boundary import (
    BOUNDARY_BUDGETS,
    BoundaryGates,
    aggregate_boundary_runs,
    approximate_mfe_views,
    load_custom_pools,
    select_boundary_policy,
    simulate_adaptive_pool,
)
from protofuse.sai.custom_mfe_residual import (
    ResidualGates,
    fit_residual_candidates,
    load_residual_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = REPO_ROOT / "data/analysis/custom-egfp-lung"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ANALYSIS_ROOT / "experiment-manifest.json"
    )
    parser.add_argument(
        "--residual-report",
        type=Path,
        default=ANALYSIS_ROOT / "residual-experiment.json",
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
        "--development-dir", type=Path, default=ANALYSIS_ROOT / "development"
    )
    parser.add_argument(
        "--external-dir", type=Path, default=ANALYSIS_ROOT / "frozen-audit"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ANALYSIS_ROOT / "adaptive-boundary-experiment.json",
    )
    parser.add_argument(
        "--exact-mfe-extrema",
        action="store_true",
        help="Exact-rescore current MFE normalization extrema until closure.",
    )
    parser.add_argument(
        "--mfe-tail-budget",
        type=int,
        default=0,
        help="Exact-rescore this many current MFE candidates at each tail.",
    )
    return parser


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def _paths(directory: Path, groups: tuple[str, ...]) -> tuple[Path, ...]:
    selected = tuple(
        path
        for path in sorted(directory.glob("*.jsonl"))
        if any(group in path.stem for group in groups)
    )
    if len(selected) != len(groups):
        raise ValueError(f"expected {len(groups)} traces in {directory}; found {len(selected)}")
    return selected


def main() -> int:
    args = _parser().parse_args()
    if args.mfe_tail_budget < 0:
        raise ValueError("CUSTOM MFE tail budget must be non-negative")
    mfe_tail_budget = max(args.mfe_tail_budget, int(args.exact_mfe_extrema))
    manifest = json.loads(args.manifest.read_text())
    residual_report = json.loads(args.residual_report.read_text())
    if residual_report.get("external_audit", {}).get("passed") is not True:
        raise ValueError("adaptive boundary requires the frozen passing residual experiment")
    development = manifest["development"]
    train_groups = tuple(development["training_groups"])
    calibration_groups = tuple(development["calibration_groups"])
    audit_groups = tuple(development["model_selection_groups"])
    external_groups = tuple(manifest["frozen_external_audit"]["group_ids"])
    gates = BoundaryGates()
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "running_development",
        "declaration": {
            "sources": ["frozen sampled-window", "frozen ridge residual"],
            "boundary_budgets": list(BOUNDARY_BUDGETS),
            "policy": (
                "Exact all uncertainty/OOD fallbacks and the provisional top-N, then "
                "exact any newly selected top-10 candidates until closure."
            ),
            "exact_mfe_extrema_closure": mfe_tail_budget > 0,
            "mfe_tail_budget": mfe_tail_budget,
            "winner_rule": (
                "Pass every gate, minimize mean exact-MFE candidate count, and prefer "
                "the simpler sampled source on an exact tie."
            ),
            "gates": gates.as_dict(),
            "cost_model": {
                "sampled_windows_per_candidate": 80,
                "exact_windows_per_candidate": 638,
                "disclosure": (
                    "Theoretical MFE work only; end-to-end timing requires a runtime "
                    "implementation and a fresh counterbalanced experiment."
                ),
            },
            "external_disclosure": (
                "External pools are group/hash-disjoint from development but were opened "
                "by earlier sampled and residual audits; they are not confirmation data."
            ),
        },
    }
    _write(args.out, payload)

    development_dataset = load_residual_dataset(
        args.development_cache,
        expected_trace_sha256=tuple(residual_report["development"]["trace_sha256"]),
    )
    candidates = fit_residual_candidates(
        development_dataset,
        train_groups=train_groups,
        calibration_groups=calibration_groups,
        gates=ResidualGates(),
    )
    selected_model = residual_report["selected_candidate"]
    residual_candidate = next(
        candidate for candidate in candidates if candidate.family == selected_model["family"]
    )
    if residual_candidate.model_sha256 != selected_model["model_sha256"]:
        raise ValueError("adaptive boundary refit does not match the frozen residual hash")
    development_views = approximate_mfe_views(
        development_dataset,
        residual_candidate,
    )
    development_pools = load_custom_pools(
        _paths(args.development_dir, audit_groups),
        expected_groups=set(audit_groups),
    )
    policies: list[dict[str, Any]] = []
    for view in development_views:
        for budget in BOUNDARY_BUDGETS:
            policies.append(
                aggregate_boundary_runs(
                    [
                        simulate_adaptive_pool(
                            pool,
                            view,
                            boundary_budget=budget,
                            exact_mfe_extrema=args.exact_mfe_extrema,
                            mfe_tail_budget=mfe_tail_budget,
                        )
                        for pool in development_pools
                    ],
                    gates=gates,
                )
            )
    payload["development"] = {
        "groups": list(audit_groups),
        "policies": policies,
    }
    winner = select_boundary_policy(policies)
    if winner is None:
        payload["status"] = "development_rejected"
        payload["selected_policy"] = None
        payload["external_audit"] = {"status": "not_opened"}
        _write(args.out, payload)
        print(f"status={payload['status']} report={args.out}")
        return 2
    payload["status"] = "policy_frozen"
    payload["selected_policy"] = {
        key: value for key, value in winner.items() if key != "runs"
    }
    _write(args.out, payload)

    external_dataset = load_residual_dataset(
        args.external_cache,
        expected_trace_sha256=tuple(residual_report["external_audit"]["trace_sha256"]),
    )
    external_views = approximate_mfe_views(external_dataset, residual_candidate)
    external_view = next(
        view for view in external_views if view.source == winner["source"]
    )
    external_pools = load_custom_pools(
        _paths(args.external_dir, external_groups),
        expected_groups=set(external_groups),
    )
    external = aggregate_boundary_runs(
        [
            simulate_adaptive_pool(
                pool,
                external_view,
                boundary_budget=int(winner["boundary_budget"]),
                exact_mfe_extrema=args.exact_mfe_extrema,
                mfe_tail_budget=mfe_tail_budget,
            )
            for pool in external_pools
        ],
        gates=gates,
    )
    payload["external_audit"] = {
        **external,
        "groups": list(external_groups),
        "group_disjoint": True,
        "pristine_confirmation": False,
    }
    payload["status"] = (
        "external_pass_requires_runtime_and_fresh_confirmation"
        if external["passed"]
        else "external_rejected"
    )
    _write(args.out, payload)
    print(
        f"selected={winner['source']} top-{winner['boundary_budget']} "
        f"external_recall={external['mean_top10_recall']:.3f} "
        f"work_avoided={external['mean_mfe_work_avoided_fraction']:.3f}"
    )
    print(f"status={payload['status']} report={args.out}")
    return 0 if external["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
