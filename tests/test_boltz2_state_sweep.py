from proto_language.optimizer.rejection_sampling_optimizer import RejectionSamplingOptimizer

from protofuse.phillip.program_builders import (
    build_boltz2_state_sweep_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.registries import lookup_registry, profile_for_fixture


def test_boltz2_state_sweep_registry_compiles() -> None:
    from protofuse.phillip.compiler import compile_proto_plan
    from protofuse.phillip.topology import recommend_topologies

    spec = load_fixture_spec("boltz2-state-sweep")
    profile = profile_for_fixture("boltz2-state-sweep")
    plan = compile_proto_plan(
        spec,
        recommend_topologies(spec)[0],
        registry=lookup_registry(profile.registry_name),
    )
    assert plan.bindings
    assert not plan.unresolved


def test_boltz2_state_sweep_fixture_is_valid() -> None:
    spec = load_fixture_spec("boltz2-state-sweep")
    assert spec.global_parameters["workload"] == "boltz2_state_sweep"
    assert spec.global_parameters["dominant_state_pdb"] == "4GBY"
    assert spec.global_parameters["alternative_state_pdb"] == "4GBZ"
    assert int(spec.global_parameters["num_samples"]) == 55


def test_boltz2_state_sweep_smoke_build_program() -> None:
    spec = load_fixture_spec("boltz2-state-sweep")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_boltz2_state_sweep_program(params)

    assert len(program.optimizers) == 1
    optimizer = program.optimizers[0]
    assert isinstance(optimizer, RejectionSamplingOptimizer)
    assert optimizer.config.num_samples == 6
    assert optimizer.config.num_results == 3

    segment = program.constructs[0].segments[0]
    assert segment.sequence_type == "protein"
    assert segment.sequence_length == 214
    assert params["dominant_state_pdb"] == "4AKE"
    assert params["alternative_state_pdb"] == "1AKE"
    assert {item.label for item in optimizer.constraints} == {
        "plddt",
        "rmsd_dominant",
        "rmsd_alternative",
        "length",
    }


def test_boltz2_state_sweep_full_build_program() -> None:
    spec = load_fixture_spec("boltz2-state-sweep")
    params = resolve_workload_params(spec, tier="full")
    program = build_boltz2_state_sweep_program(params)

    optimizer = program.optimizers[0]
    assert optimizer.config.num_samples == 55
    assert optimizer.config.num_results == 10

    segment = program.constructs[0].segments[0]
    assert segment.sequence_length == 491
    assert params["dominant_state_pdb"] == "4GBY"
    assert params["alternative_state_pdb"] == "4GBZ"

    dominant_cfg = next(
        item.function_config for item in optimizer.constraints if item.label == "rmsd_dominant"
    )
    alternative_cfg = next(
        item.function_config
        for item in optimizer.constraints
        if item.label == "rmsd_alternative"
    )
    assert dominant_cfg.structure_tool == "boltz2"
    assert alternative_cfg.structure_tool == "boltz2"
    assert dominant_cfg.boltz2_config.subsample_msa is True
    assert int(dominant_cfg.boltz2_config.max_msa_seqs) == 512
    assert optimizer.config.proposal_source == "generated"
    assert len(optimizer.generators) == 1
