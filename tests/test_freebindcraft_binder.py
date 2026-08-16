from protofuse.phillip.program_builders import (
    build_freebindcraft_binder_program,
    load_fixture_spec,
    resolve_workload_params,
)


def test_freebindcraft_fixture_is_valid() -> None:
    spec = load_fixture_spec("freebindcraft-binder")
    assert spec.global_parameters["workload"] == "freebindcraft_binder"
    assert int(spec.global_parameters["binder_length_aa"]) == 70
    assert int(spec.global_parameters["num_samples"]) == 50


def test_freebindcraft_smoke_build_program() -> None:
    spec = load_fixture_spec("freebindcraft-binder")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_freebindcraft_binder_program(params)

    assert len(program.optimizers) == 1
    optimizer = program.optimizers[0]
    assert optimizer.config.num_samples == 5

    binder = program.constructs[0].segments[0]
    target = program.constructs[0].segments[1]
    assert binder.sequence_type == "protein"
    assert binder.sequence_length == 50
    assert target.sequence_type == "protein"
    assert target.sequence_length > 0
    assert len(optimizer.constraints) == 5
    assert {item.label for item in optimizer.constraints} == {
        "iptm",
        "ipae",
        "plddt",
        "rmsd",
        "length",
    }


def test_freebindcraft_full_build_program() -> None:
    spec = load_fixture_spec("freebindcraft-binder")
    params = resolve_workload_params(spec, tier="full")
    program = build_freebindcraft_binder_program(params)

    binder = program.constructs[0].segments[0]
    assert binder.sequence_length == 70
    assert program.optimizers[0].config.num_samples == 50
