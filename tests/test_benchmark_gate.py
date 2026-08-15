from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from protofuse.integration import DNA_BASELINE_REGISTRY
from protofuse.phillip.benchmark import compare_benchmark, run_baseline_benchmark
from protofuse.phillip.pipeline import run_pipeline
from protofuse.phillip.profiler import ProfiledRun
from protofuse.phillip.proto_builder import build_baseline_program
from protofuse.phillip.runs import HANDOFF_ROOT, phillip_handoff_dir
from protofuse.scientific_agent import ScientificAgent

REPO_ROOT = Path(__file__).resolve().parents[1]
DECISION_ID = "dnachisel-v1"
SCENARIO_ID = "dnachisel-gc-optimization"


class FakeBackend:
    def __init__(self, spec_json: str) -> None:
        self.spec_json = spec_json

    def extract_json(self, *, system: str, prompt: str) -> str:
        return self.spec_json


def _fake_profiled_run(*, wall_time_ms: float = 100.0) -> ProfiledRun:
    trace = {
        "schema_version": "1.0",
        "total_wall_time_ms": wall_time_ms,
        "nodes": [
            {
                "node_id": "cst:0:windowed_gc_content",
                "kind": "constraint",
                "calls": 50,
                "duration_ms_total": 60.0,
                "duration_ms_mean": 1.2,
                "cache_hits": 0,
                "cache_misses": 50,
                "quality_contribution": "high",
                "measurement": "measured",
            },
            {
                "node_id": "opt:0:mcmc_refinement",
                "kind": "optimizer",
                "calls": 50,
                "duration_ms_total": 40.0,
                "duration_ms_mean": 0.8,
                "cache_hits": 0,
                "cache_misses": 50,
                "quality_contribution": "orchestration",
                "measurement": "measured",
            },
        ],
    }
    quality = {"scores": {"windowed_gc_content": 0.0, "homopolymer": 0.0}, "final_energy": 0.0}
    invariants = {"graph_invariants": [], "all_scores_pass": True, "threshold_violations": []}
    return ProfiledRun(
        wall_time_ms=wall_time_ms,
        trace=trace,
        invariants=invariants,
        quality=quality,
        constraint_evaluations=50,
    )


def test_build_baseline_program_for_pipeline_1() -> None:
    program = build_baseline_program("balanced-gc")
    assert len(program.optimizers) == 1


@patch("protofuse.phillip.benchmark.profile_program_run")
def test_run_baseline_benchmark_writes_profile_measured(mock_profile) -> None:
    mock_profile.return_value = _fake_profiled_run(wall_time_ms=120.0)
    result = run_baseline_benchmark(
        decision_id=DECISION_ID,
        scenario_id=SCENARIO_ID,
        seed=0,
        repetitions=1,
    )
    measured_path = Path(result["profile_measured_path"])
    assert measured_path.exists()
    payload = json.loads(measured_path.read_text())
    assert payload["nodes"][0]["measurement"] == "measured"


@patch("protofuse.phillip.benchmark.run_candidate_benchmark")
@patch("protofuse.phillip.benchmark.run_baseline_benchmark")
def test_compare_benchmark_writes_report_in_phillip_lane(
    mock_baseline,
    mock_candidate,
) -> None:
    mock_baseline.return_value = {
        "decision_id": DECISION_ID,
        "variant": "baseline",
        "runs": 1,
        "median_wall_time_ms": 100.0,
        "profile_measured_path": str(phillip_handoff_dir(DECISION_ID) / "profile_measured.json"),
    }
    mock_candidate.return_value = {
        "decision_id": DECISION_ID,
        "variant": "candidate",
        "runs": 1,
        "median_wall_time_ms": 80.0,
    }

    trace = _fake_profiled_run().trace
    quality = _fake_profiled_run().quality
    invariants = _fake_profiled_run().invariants

    from protofuse.phillip.runs import variant_dir, write_run_artifacts

    for variant in ("baseline", "candidate"):
        run_dir = variant_dir(DECISION_ID, variant) / "test-run"
        write_run_artifacts(
            run_dir,
            {
                "run_config.json": {"run_id": "test-run", "variant": variant},
                "trace.json": trace,
                "invariants.json": invariants,
                "quality.json": quality,
            },
        )

    result = compare_benchmark(
        decision_id=DECISION_ID,
        scenario_id=SCENARIO_ID,
        repetitions=1,
    )
    report_path = phillip_handoff_dir(DECISION_ID) / "benchmark_report.json"
    summary_path = phillip_handoff_dir(DECISION_ID) / "benchmark_summary.md"
    assert report_path.exists()
    assert summary_path.exists()
    assert result.recommendation in {"pass", "fail"}
    assert not (HANDOFF_ROOT / "sai_to_phillip" / DECISION_ID / "benchmark_report.json").exists()


def test_pipeline_1_regression_still_executable(example_spec) -> None:
    result = run_pipeline(
        "benchmark regression",
        ScientificAgent(FakeBackend(example_spec.model_dump_json())),
        registry=DNA_BASELINE_REGISTRY,
    )
    assert result.plan.executable
