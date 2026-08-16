from proto_language.optimizer.cycling_optimizer import CyclingOptimizer

from protofuse.phillip.program_builders import (
    build_rfdiffusion3_boltz2_binder_program,
    load_fixture_spec,
    resolve_workload_params,
)


def test_rfdiffusion3_fixture_is_valid() -> None:
    spec = load_fixture_spec("rfdiffusion3-boltz2-binder")
    assert spec.global_parameters["workload"] == "rfdiffusion3_boltz2_binder"
    assert int(spec.global_parameters["num_steps"]) == 10


def test_rfdiffusion3_smoke_build_program() -> None:
    spec = load_fixture_spec("rfdiffusion3-boltz2-binder")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_rfdiffusion3_boltz2_binder_program(params)

    optimizer = program.optimizers[0]
    assert isinstance(optimizer, CyclingOptimizer)
    assert optimizer.config.num_steps == 2
    binder = program.constructs[0].segments[0]
    assert binder.sequence_length == 50
    assert {item.label for item in optimizer.constraints} == {"iptm", "plddt", "length"}
