import importlib.util
from pathlib import Path

from protofuse.phillip import compile_proto_plan, generate_program_sources, recommend_topologies
from protofuse.phillip.program_builders import (
    build_symmetric_oligomer_ring_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.registries import lookup_registry, profile_for_fixture
from protofuse.program_collection import load_collection

REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = REPO_ROOT / "proto_programs/generated/symmetric-oligomer-ring"


def test_symmetric_oligomer_fixture_is_valid() -> None:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    assert spec.global_parameters["workload"] == "symmetric_oligomer_ring"
    assert int(spec.global_parameters["symmetry_order"]) == 6
    assert int(spec.global_parameters["n_pool"]) == 1000


def test_symmetric_oligomer_smoke_params() -> None:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier="smoke")
    assert params["symmetry_order"] == 3
    assert params["n_pool"] == 100
    assert params["segment_length_aa"] == 60
    assert params["num_samples"] == 5


def test_symmetric_oligomer_full_params() -> None:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier="full")
    assert params["symmetry_order"] == 6
    assert params["n_pool"] == 1000
    assert params["segment_length_aa"] == 80
    assert params["num_samples"] == 20


def test_build_smoke_program_structure() -> None:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_symmetric_oligomer_ring_program(params)

    assert len(program.optimizers) == 1
    optimizer = program.optimizers[0]
    assert optimizer.config.num_samples == 5
    assert len(optimizer.constraints) == 5
    monomer = program.constructs[0].segments[0]
    assert monomer.sequence_type == "protein"
    assert monomer.sequence_length == 60
    symmetry = next(item for item in optimizer.constraints if item.label == "protein_symmetry_ring")
    assert len(symmetry.inputs) == 3


def test_build_full_program_structure() -> None:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier="full")
    program = build_symmetric_oligomer_ring_program(params)

    optimizer = program.optimizers[0]
    assert optimizer.config.num_samples == 20
    monomer = program.constructs[0].segments[0]
    assert monomer.sequence_length == 80
    symmetry = next(item for item in optimizer.constraints if item.label == "protein_symmetry_ring")
    assert len(symmetry.inputs) == 6


def test_generate_symmetric_oligomer_matches_committed_sources() -> None:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    profile = profile_for_fixture("symmetric-oligomer-ring")
    recommendations = recommend_topologies(spec)
    plan = compile_proto_plan(
        spec,
        recommendations[0],
        registry=lookup_registry(profile.registry_name),
        device="modal",
    )
    generated = generate_program_sources(spec, plan, profile=profile)

    for filename, source in generated.items():
        committed = (COLLECTION / filename).read_text()
        assert source == committed


def test_symmetric_oligomer_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(COLLECTION, require_reviewed=True)

    assert loaded.manifest.collection_id == "symmetric-oligomer-ring"
    assert loaded.manifest.methodology_id == "symmetric-oligomer-ring-v1"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2


def test_symmetric_oligomer_smoke_design_builds_program() -> None:
    spec = importlib.util.spec_from_file_location(
        "symmetric_design_002",
        COLLECTION / "design_002.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    program = module.build_program()
    monomer = program.constructs[0].segments[0]
    assert monomer.sequence_length == 60
    assert program.optimizers[0].config.num_samples == 5
