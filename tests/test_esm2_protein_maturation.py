from protofuse.phillip.program_builders import (
    build_esm2_protein_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.workload_preflight import run_preflight


def test_esm2_fixture_is_valid() -> None:
    spec = load_fixture_spec("esm2-protein-maturation")
    assert spec.global_parameters["workload"] == "esm2_protein_maturation"
    assert int(spec.global_parameters["segment_length_aa"]) == 129


def test_esm2_smoke_build_program() -> None:
    spec = load_fixture_spec("esm2-protein-maturation")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_esm2_protein_maturation_program(params, region_pass=0)

    assert len(program.optimizers) == 1
    segment = program.constructs[0].segments[0]
    assert segment.sequence_type == "protein"
    assert segment.sequence_length == 80
    assert str(segment.original_sequence) == params["seed_sequence"]


def test_esm2_full_build_program() -> None:
    spec = load_fixture_spec("esm2-protein-maturation")
    params = resolve_workload_params(spec, tier="full")
    program = build_esm2_protein_maturation_program(params, region_pass=0)

    segment = program.constructs[0].segments[0]
    assert segment.sequence_length == 129
    assert len(program.optimizers[0].constraints) == 6


def test_esm2_preflight_build_only() -> None:
    report = run_preflight("esm2-protein-maturation", target_length=80, quiet=True)
    assert report.classification == "ok"
    assert report.target_length == 80
