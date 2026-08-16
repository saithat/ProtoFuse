from protofuse.phillip.program_builders import (
    build_ligandmpnn_enzyme_redesign_program,
    load_fixture_spec,
    resolve_workload_params,
)
from proto_language.optimizer.mcmc_optimizer import MCMCOptimizer


def test_ligandmpnn_fixture_is_valid() -> None:
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    assert spec.global_parameters["workload"] == "ligandmpnn_enzyme_redesign"
    assert spec.global_parameters["enzyme_pdb"] == "3HTB"


def test_ligandmpnn_smoke_build_program() -> None:
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_ligandmpnn_enzyme_redesign_program(params)

    optimizer = program.optimizers[0]
    assert isinstance(optimizer, MCMCOptimizer)
    assert optimizer.config.num_steps == 20
    enzyme = program.constructs[0].segments[0]
    assert enzyme.sequence_length == 163
    assert {item.label for item in optimizer.constraints} == {
        "mpnn_probability",
        "structure_plddt",
        "protein_length",
    }
