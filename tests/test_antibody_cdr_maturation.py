import importlib.util
from pathlib import Path

from protofuse.phillip import compile_proto_plan, generate_program_sources, recommend_topologies
from protofuse.phillip.program_builders import (
    build_antibody_cdr_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.registries import lookup_registry, profile_for_fixture
from protofuse.program_collection import load_collection

REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = REPO_ROOT / "proto_programs/generated/antibody-cdr-maturation"


def test_antibody_fixture_is_valid() -> None:
    spec = load_fixture_spec("antibody-cdr-maturation")
    assert spec.global_parameters["workload"] == "antibody_cdr_maturation"
    assert len(spec.global_parameters["framework_sequence"]) == 121
    assert spec.global_parameters["cdr_regions"] == [[26, 38], [55, 65], [95, 103]]


def test_antibody_smoke_params() -> None:
    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier="smoke")
    assert params["num_steps"] == 30
    assert params["max_region_passes"] == 1
    assert params["esm2_checkpoint"] == "esm2_t6_8M_UR50D"


def test_antibody_full_params() -> None:
    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier="full")
    assert params["num_steps"] == 100
    assert params["max_region_passes"] == 3
    assert params["esm2_checkpoint"] == "esm2_t33_650M_UR50D"


def test_build_smoke_program_structure() -> None:
    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_antibody_cdr_maturation_program(params, region_pass=0)

    assert len(program.optimizers) == 1
    optimizer = program.optimizers[0]
    assert optimizer.config.num_steps == 30
    assert len(optimizer.constraints) == 4
    assert len(program.constructs[0].segments) == 3
    antibody = program.constructs[0].segments[0]
    assert antibody.sequence_length == 121
    fixed = optimizer.generators[0].config.masking_strategy.fixed_positions
    assert fixed is not None
    assert 26 in fixed
    assert 27 not in fixed
    assert 39 in fixed


def test_cdr_masking_switches_by_region_pass() -> None:
    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier="full")

    cdr1 = build_antibody_cdr_maturation_program(params, region_pass=0)
    cdr2 = build_antibody_cdr_maturation_program(params, region_pass=1)

    mask1 = cdr1.optimizers[0].generators[0].config.masking_strategy.fixed_positions
    mask2 = cdr2.optimizers[0].generators[0].config.masking_strategy.fixed_positions
    assert mask1 != mask2
    assert 56 not in mask2
    assert 27 in mask2


def test_generate_antibody_matches_committed_sources() -> None:
    spec = load_fixture_spec("antibody-cdr-maturation")
    profile = profile_for_fixture("antibody-cdr-maturation")
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


def test_antibody_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(COLLECTION, require_reviewed=True)

    assert loaded.manifest.collection_id == "antibody-cdr-maturation"
    assert loaded.manifest.methodology_id == "antibody-cdr-maturation-v1"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2


def test_antibody_smoke_design_builds_program() -> None:
    spec = importlib.util.spec_from_file_location(
        "antibody_design_002",
        COLLECTION / "design_002.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    program = module.build_program()
    antibody = program.constructs[0].segments[0]
    assert antibody.sequence_length == 121
    assert program.optimizers[0].config.num_steps == 30
