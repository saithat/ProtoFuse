import importlib.util
from pathlib import Path

from protofuse.phillip import compile_proto_plan, generate_program_sources, recommend_topologies
from protofuse.phillip.program_builders import (
    build_ppi_interface_specificity_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.registries import lookup_registry, profile_for_fixture
from protofuse.program_collection import load_collection

REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = REPO_ROOT / "proto_programs/generated/ppi-interface-specificity"


def test_ppi_fixture_is_valid() -> None:
    spec = load_fixture_spec("ppi-interface-specificity")
    assert spec.global_parameters["workload"] == "ppi_interface_specificity"
    assert len(spec.global_parameters["binder_sequence"]) == 65
    assert spec.global_parameters["target_pdb"] == "4ZQK"
    assert spec.global_parameters["off_target_pdb"] == "4RWS"
    assert spec.global_parameters["interface_regions"] == [[18, 30], [40, 52]]


def test_ppi_smoke_params() -> None:
    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier="smoke")
    assert params["num_steps"] == 20
    assert params["max_region_passes"] == 1
    assert params["proposal_generator"] == "esm2"
    assert params["esm2_checkpoint"] == "esm2_t6_8M_UR50D"


def test_ppi_full_params() -> None:
    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier="full")
    assert params["num_steps"] == 100
    assert params["max_region_passes"] == 2
    assert params["proposal_generator"] == "mpnn"


def test_build_smoke_program_structure() -> None:
    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_ppi_interface_specificity_program(params, region_pass=0)

    assert len(program.optimizers) == 1
    optimizer = program.optimizers[0]
    assert optimizer.config.num_steps == 20
    assert len(optimizer.constraints) == 4
    assert len(program.constructs[0].segments) == 3
    binder = program.constructs[0].segments[0]
    assert binder.sequence_length == 65
    fixed = optimizer.generators[0].config.masking_strategy.fixed_positions
    assert fixed is not None
    assert 18 in fixed
    assert 19 not in fixed
    assert 31 in fixed


def test_interface_masking_switches_by_region_pass() -> None:
    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier="full")

    patch1 = build_ppi_interface_specificity_program(params, region_pass=0)
    patch2 = build_ppi_interface_specificity_program(params, region_pass=1)

    gen1 = patch1.optimizers[0].generators[0]
    gen2 = patch2.optimizers[0].generators[0]
    mask1 = gen1.config.mutable_positions
    mask2 = gen2.config.mutable_positions
    assert mask1 is not None and mask2 is not None
    assert mask1.chains["A"] != mask2.chains["A"]
    assert 41 in mask2.chains["A"]
    assert 19 in mask1.chains["A"]


def test_generate_ppi_matches_committed_sources() -> None:
    spec = load_fixture_spec("ppi-interface-specificity")
    profile = profile_for_fixture("ppi-interface-specificity")
    recommendations = recommend_topologies(spec)
    plan = compile_proto_plan(
        spec,
        recommendations[0],
        registry=lookup_registry(profile.registry_name),
    )
    generated = generate_program_sources(spec, plan, profile=profile)

    for filename, source in generated.items():
        committed = (COLLECTION / filename).read_text()
        assert source == committed


def test_ppi_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(COLLECTION, require_reviewed=True)

    assert loaded.manifest.collection_id == "ppi-interface-specificity"
    assert loaded.manifest.methodology_id == "ppi-interface-specificity-v1"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2


def test_ppi_smoke_design_builds_program() -> None:
    spec = importlib.util.spec_from_file_location(
        "ppi_design_002",
        COLLECTION / "design_002.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    program = module.build_program()
    binder = program.constructs[0].segments[0]
    assert binder.sequence_length == 65
    assert program.optimizers[0].config.num_steps == 20
