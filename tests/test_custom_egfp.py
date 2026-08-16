from protofuse.phillip.program_builders import load_fixture_spec


def test_custom_egfp_fixture_is_valid() -> None:
    spec = load_fixture_spec("custom-egfp-lung")
    assert spec.paper.identifier == "10.1186/s13059-023-02868-2"
    assert spec.global_parameters["workload"] == "custom_egfp_pool"
    assert spec.global_parameters["n_pool"] == 1000
