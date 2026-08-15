import pytest

from protofuse.phillip.program_builders import load_fixture_spec, run_custom_egfp_lung


def test_custom_egfp_fixture_is_valid() -> None:
    spec = load_fixture_spec("custom-egfp-lung")
    assert spec.paper.identifier == "10.1186/s13059-023-02868-2"
    assert spec.global_parameters["workload"] == "custom_egfp_pool"
    assert spec.global_parameters["n_pool"] == 1000


def test_custom_egfp_smoke_runs_quickly() -> None:
    program, wall_ms = run_custom_egfp_lung(tier="smoke")
    sequence = program.constructs[0].joined_sequences[0].sequence
    assert len(sequence) == 720
    assert wall_ms < 30_000


@pytest.mark.slow
def test_custom_egfp_full_is_minute_scale() -> None:
    _, wall_ms = run_custom_egfp_lung(tier="full")
    assert wall_ms >= 30_000
    assert wall_ms <= 300_000
