import logging

import pytest

from protofuse.phillip.handoff_config import HANDOFF_CONFIGS
from protofuse.phillip.program_builders import load_fixture_spec, run_dnachisel_num1
from protofuse.phillip.sequence_init import estimate_filter_pass_rate, generate_filter_safe_sequence
from protofuse.phillip.workload_preflight import (
    BUILD_ONLY_PREFLIGHT_WORKLOADS,
    DNA_PREFLIGHT_WORKLOADS,
    assert_output_length,
    assert_workload_feasible,
    classify_report,
    run_isolation_ladder,
    run_preflight,
)


def test_every_reviewed_fixture_has_an_explicit_preflight_strategy() -> None:
    supported = DNA_PREFLIGHT_WORKLOADS | BUILD_ONLY_PREFLIGHT_WORKLOADS
    workloads = {
        str(load_fixture_spec(fixture_id).global_parameters.get("workload"))
        for fixture_id in HANDOFF_CONFIGS
    }

    assert workloads <= supported


def test_generate_filter_safe_sequence_passes_hard_filters() -> None:
    seq = generate_filter_safe_sequence(2808, seed=42)
    assert len(seq) == 2808
    assert all(base in "ACGT" for base in seq)


def test_filter_pass_rate_decreases_with_length() -> None:
    rate_936 = estimate_filter_pass_rate(936, n=1000, seed=0)
    rate_2808 = estimate_filter_pass_rate(2808, n=1000, seed=0)
    assert rate_936 > rate_2808
    assert rate_936 > 0.01


def test_l0_isolation_passes_at_2808() -> None:
    logging.disable(logging.CRITICAL)
    ladder = run_isolation_ladder(2808, num_steps=20)
    l0 = next(step for step in ladder if step.level == "L0")
    assert l0.passed
    assert l0.output_length == 2808


def test_preflight_2808_ok_with_seed_init() -> None:
    logging.disable(logging.CRITICAL)
    report = run_preflight("dnachisel-num1", target_length=2808, filter_samples=200, num_steps=30)
    assert report.classification == "ok"
    assert_workload_feasible(report)


def test_classify_platform_error_when_l0_fails() -> None:
    from protofuse.phillip.workload_preflight import LadderStepResult

    steps = [
        LadderStepResult(level="L0", output_length=0, expected_length=100, passed=False),
    ]
    assert classify_report(steps) == "platform_error"


def test_dnachisel_num1_fixture_length() -> None:
    spec = load_fixture_spec("dnachisel-num1")
    assert int(spec.global_parameters["segment_length_bp"]) == 936


def test_dnachisel_num1_smoke_output_length() -> None:
    logging.disable(logging.CRITICAL)
    program, wall_ms = run_dnachisel_num1(tier="smoke")
    assert_output_length(program, 100)
    assert wall_ms < 30_000


@pytest.mark.slow
def test_dnachisel_num1_full_output_length() -> None:
    logging.disable(logging.CRITICAL)
    spec = load_fixture_spec("dnachisel-num1")
    expected = int(spec.global_parameters["segment_length_bp"])
    program, wall_ms = run_dnachisel_num1(tier="full")
    assert_output_length(program, expected)
    assert wall_ms >= 10_000
