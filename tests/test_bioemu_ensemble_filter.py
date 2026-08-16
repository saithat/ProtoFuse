from proto_language.optimizer.mcmc_optimizer import MCMCOptimizer

from protofuse.phillip.program_builders import (
    build_bioemu_ensemble_filter_program,
    load_fixture_spec,
    resolve_workload_params,
)


def test_bioemu_fixture_is_valid() -> None:
    spec = load_fixture_spec("bioemu-ensemble-filter")
    assert spec.global_parameters["workload"] == "bioemu_ensemble_filter"
    assert spec.global_parameters["target_pdb"] == "2LYZ"


def test_bioemu_smoke_build_program() -> None:
    spec = load_fixture_spec("bioemu-ensemble-filter")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_bioemu_ensemble_filter_program(params)

    optimizer = program.optimizers[0]
    assert isinstance(optimizer, MCMCOptimizer)
    assert optimizer.config.num_steps == 20
    segment = program.constructs[0].segments[0]
    assert segment.sequence_length == 80
    assert {item.label for item in optimizer.constraints} == {
        "ensemble_rmsd",
        "structure_plddt",
        "protein_length",
    }
