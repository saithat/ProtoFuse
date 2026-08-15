"""Baseline vs candidate benchmark harness for Decision 2."""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from protofuse.integration import DNA_BASELINE_REGISTRY, DNA_CHISEL_REGISTRY
from protofuse.phillip.profiler import aggregate_profile_from_trace, load_graph, profile_program_run
from protofuse.phillip.proto_builder import build_baseline_program
from protofuse.phillip.runs import (
    HANDOFF_ROOT,
    REPO_ROOT,
    RunRecord,
    list_run_dirs,
    new_run_id,
    phillip_handoff_dir,
    sai_handoff_dir,
    variant_dir,
    write_run_manifest,
)
from protofuse.sai.protocstage import build_candidate_program

QUALITY_EPSILON = 1e-9


@dataclass(frozen=True)
class BenchmarkCompareResult:
    decision_id: str
    scenario_id: str
    recommendation: Literal["pass", "fail"]
    report: dict[str, Any]
    summary_md: str


def run_baseline_benchmark(
    *,
    decision_id: str,
    scenario_id: str,
    seed: int = 0,
    repetitions: int = 1,
    device: str = "local",
    handoff_root: Path = HANDOFF_ROOT,
) -> dict[str, Any]:
    graph = load_graph(decision_id, handoff_root)
    profiled_runs = []
    for offset in range(repetitions):
        run_id = new_run_id()
        record = RunRecord(
            run_id=run_id,
            variant="baseline",
            decision_id=decision_id,
            scenario_id=scenario_id,
            seed=seed + offset,
            device=device,
            run_dir=variant_dir(decision_id, "baseline") / run_id,
        )
        program = build_baseline_program(scenario_id, seed=record.seed)
        profiled_runs.append(
            profile_program_run(program, graph, record=record, cache_stats={})
        )

    manifest = _build_run_manifest(
        decision_id=decision_id,
        scenario_id=scenario_id,
        seed=seed,
        repetitions=repetitions,
        device=device,
        handoff_root=handoff_root,
    )
    write_run_manifest(decision_id, manifest)

    measured_profile = aggregate_profile_from_trace(
        profiled_runs[-1].trace,
        device=device,
        seed=seed,
    )
    handoff_dir = phillip_handoff_dir(decision_id)
    handoff_dir.mkdir(parents=True, exist_ok=True)
    (handoff_dir / "profile_measured.json").write_text(
        json.dumps(measured_profile, indent=2) + "\n"
    )
    return {
        "decision_id": decision_id,
        "variant": "baseline",
        "runs": len(profiled_runs),
        "median_wall_time_ms": _median([run.wall_time_ms for run in profiled_runs]),
        "profile_measured_path": str(
            (handoff_dir / "profile_measured.json").relative_to(REPO_ROOT)
        ),
    }


def run_candidate_benchmark(
    *,
    decision_id: str,
    scenario_id: str,
    seed: int = 0,
    repetitions: int = 1,
    device: str = "local",
    handoff_root: Path = HANDOFF_ROOT,
) -> dict[str, Any]:
    graph = load_graph(decision_id, handoff_root)
    profiled_runs = []
    for offset in range(repetitions):
        run_id = new_run_id()
        record = RunRecord(
            run_id=run_id,
            variant="candidate",
            decision_id=decision_id,
            scenario_id=scenario_id,
            seed=seed + offset,
            device=device,
            run_dir=variant_dir(decision_id, "candidate") / run_id,
        )
        baseline = build_baseline_program(scenario_id, seed=record.seed)
        program, cache_stats = build_candidate_program(
            baseline,
            decision_id=decision_id,
            handoff_root=handoff_root,
        )
        profiled_runs.append(
            profile_program_run(program, graph, record=record, cache_stats=cache_stats)
        )
    return {
        "decision_id": decision_id,
        "variant": "candidate",
        "runs": len(profiled_runs),
        "median_wall_time_ms": _median([run.wall_time_ms for run in profiled_runs]),
    }


def compare_benchmark(
    *,
    decision_id: str,
    scenario_id: str | None = None,
    seed: int = 0,
    repetitions: int | None = None,
    device: str = "local",
    handoff_root: Path = HANDOFF_ROOT,
    skip_candidate: bool = False,
) -> BenchmarkCompareResult:
    benchmark_plan = json.loads(
        (sai_handoff_dir(decision_id) / "benchmark_plan.json").read_text()
    )
    scenario_id = scenario_id or _scenario_from_graph(decision_id, handoff_root)
    repetitions = repetitions or int(benchmark_plan.get("repetitions", 1))
    plan_seed = int(benchmark_plan.get("seed", seed))

    baseline_result = run_baseline_benchmark(
        decision_id=decision_id,
        scenario_id=scenario_id,
        seed=plan_seed,
        repetitions=repetitions,
        device=device,
        handoff_root=handoff_root,
    )
    candidate_result: dict[str, Any] | None = None
    if not skip_candidate:
        candidate_result = run_candidate_benchmark(
            decision_id=decision_id,
            scenario_id=scenario_id,
            seed=plan_seed,
            repetitions=repetitions,
            device=device,
            handoff_root=handoff_root,
        )

    baseline_runs = _load_variant_runs(decision_id, "baseline")
    candidate_runs = _load_variant_runs(decision_id, "candidate")
    exactness = _exactness_check(baseline_runs, candidate_runs)

    metrics = _evaluate_metrics(
        benchmark_plan,
        baseline_median_ms=baseline_result["median_wall_time_ms"],
        candidate_median_ms=(
            None if candidate_result is None else candidate_result["median_wall_time_ms"]
        ),
        baseline_runs=baseline_runs,
        candidate_runs=candidate_runs,
        skip_candidate=skip_candidate,
    )
    if not skip_candidate:
        metrics.append(
            {
                "name": "exactness",
                "details": exactness,
                "passed": exactness.get("scores_within_epsilon", False)
                and exactness.get("invariants_match", False),
            }
        )
    recommendation: Literal["pass", "fail"] = (
        "pass" if all(item["passed"] for item in metrics) else "fail"
    )

    report = {
        "schema_version": "1.0",
        "decision_id": decision_id,
        "scenario_id": scenario_id,
        "benchmark_plan_hash": _file_hash(sai_handoff_dir(decision_id) / "benchmark_plan.json"),
        "recommendation": recommendation,
        "baseline": baseline_result,
        "candidate": candidate_result,
        "metrics": metrics,
        "exactness": exactness,
    }
    summary_md = _render_summary(report)
    handoff_dir = phillip_handoff_dir(decision_id)
    handoff_dir.mkdir(parents=True, exist_ok=True)
    (handoff_dir / "benchmark_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (handoff_dir / "benchmark_summary.md").write_text(summary_md)
    return BenchmarkCompareResult(
        decision_id=decision_id,
        scenario_id=scenario_id,
        recommendation=recommendation,
        report=report,
        summary_md=summary_md,
    )


def _build_run_manifest(
    *,
    decision_id: str,
    scenario_id: str,
    seed: int,
    repetitions: int,
    device: str,
    handoff_root: Path,
) -> dict[str, Any]:
    benchmark_plan_path = sai_handoff_dir(decision_id) / "benchmark_plan.json"
    return {
        "schema_version": "1.0",
        "decision_id": decision_id,
        "scenario_id": scenario_id,
        "seed": seed,
        "repetitions": repetitions,
        "device": device,
        "benchmark_plan_hash": _file_hash(benchmark_plan_path),
        "handoff_root": str(handoff_root),
    }


def _scenario_from_graph(decision_id: str, handoff_root: Path) -> str:
    graph = load_graph(decision_id, handoff_root)
    return graph["scenario_id"]


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _load_variant_runs(decision_id: str, variant: str) -> list[dict[str, Any]]:
    runs = []
    for run_dir in list_run_dirs(decision_id, variant):  # type: ignore[arg-type]
        runs.append(
            {
                "run_id": run_dir.name,
                "trace": json.loads((run_dir / "trace.json").read_text()),
                "invariants": json.loads((run_dir / "invariants.json").read_text()),
                "quality": json.loads((run_dir / "quality.json").read_text()),
            }
        )
    return runs


def _exactness_check(
    baseline_runs: list[dict[str, Any]],
    candidate_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not baseline_runs or not candidate_runs:
        return {"status": "skipped", "reason": "missing baseline or candidate runs"}
    baseline = baseline_runs[-1]
    candidate = candidate_runs[-1]
    baseline_scores = baseline["quality"].get("scores", {})
    candidate_scores = candidate["quality"].get("scores", {})
    score_delta = {
        key: abs(float(candidate_scores.get(key, 0.0)) - float(baseline_scores.get(key, 0.0)))
        for key in sorted(set(baseline_scores) | set(candidate_scores))
    }
    scores_match = all(delta <= QUALITY_EPSILON for delta in score_delta.values())
    return {
        "status": "checked",
        "invariants_match": (
            baseline["invariants"].get("all_scores_pass")
            == candidate["invariants"].get("all_scores_pass")
        ),
        "scores_within_epsilon": scores_match,
        "score_delta": score_delta,
    }


def _evaluate_metrics(
    benchmark_plan: dict[str, Any],
    *,
    baseline_median_ms: float,
    candidate_median_ms: float | None,
    baseline_runs: list[dict[str, Any]],
    candidate_runs: list[dict[str, Any]],
    skip_candidate: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for metric in benchmark_plan.get("metrics", []):
        name = metric["name"]
        if name == "total_wall_time_ms":
            if skip_candidate or candidate_median_ms is None:
                passed = True
                ratio = None
            else:
                ratio = candidate_median_ms / baseline_median_ms if baseline_median_ms else 1.0
                passed = ratio <= float(metric.get("pass_threshold_ratio", 1.0))
            results.append(
                {
                    "name": name,
                    "baseline": baseline_median_ms,
                    "candidate": candidate_median_ms,
                    "ratio": ratio,
                    "passed": passed,
                }
            )
        elif name == "constraint_evaluations":
            baseline_count = _constraint_eval_total(baseline_runs)
            candidate_count = _constraint_eval_total(candidate_runs) if candidate_runs else None
            if skip_candidate or candidate_count is None:
                passed = True
            else:
                passed = candidate_count == baseline_count
            results.append(
                {
                    "name": name,
                    "baseline": baseline_count,
                    "candidate": candidate_count,
                    "passed": passed,
                }
            )
        elif name == "scientific_invariants":
            baseline_ok = all(run["invariants"].get("all_scores_pass") for run in baseline_runs)
            candidate_ok = (
                all(run["invariants"].get("all_scores_pass") for run in candidate_runs)
                if candidate_runs
                else True
            )
            results.append(
                {
                    "name": name,
                    "baseline": baseline_ok,
                    "candidate": candidate_ok,
                    "passed": baseline_ok and candidate_ok,
                }
            )
        else:
            results.append({"name": name, "passed": False, "reason": "unknown metric"})
    return results


def _constraint_eval_total(runs: list[dict[str, Any]]) -> int:
    if not runs:
        return 0
    trace = runs[-1]["trace"]
    return sum(node["calls"] for node in trace["nodes"] if node["kind"] == "constraint")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_summary(report: dict[str, Any]) -> str:
    lines = [
        f"# Benchmark summary: {report['decision_id']}",
        "",
        f"- Scenario: `{report['scenario_id']}`",
        f"- Recommendation: **{report['recommendation']}**",
        f"- Baseline median wall time (ms): {report['baseline']['median_wall_time_ms']:.2f}",
    ]
    if report.get("candidate"):
        lines.append(
            "- Candidate median wall time (ms): "
            f"{report['candidate']['median_wall_time_ms']:.2f}"
        )
    lines.append("")
    lines.append("## Metrics")
    for metric in report["metrics"]:
        status = "pass" if metric["passed"] else "fail"
        lines.append(f"- `{metric['name']}`: {status}")
    lines.append("")
    lines.append(
        "Sai: review this report and update "
        f"`sai_to_phillip/{report['decision_id']}/decision_record.md`."
    )
    return "\n".join(lines) + "\n"


def registry_for_scenario(scenario_id: str) -> dict[str, str]:
    if scenario_id == "balanced-gc":
        return DNA_BASELINE_REGISTRY
    return DNA_CHISEL_REGISTRY
