from __future__ import annotations

import json
from pathlib import Path

import pytest
from proto_language.core import Sequence
from proto_language.optimizer import BeamSearchOptimizer, RejectionSamplingOptimizer
from proto_tools.entities.structures.structure import Structure

from protofuse.phillip.compiler import compile_proto_plan
from protofuse.phillip.generator import generate_program_sources
from protofuse.phillip.program_builders import (
    build_af3_boltz2_state_sweep_program,
    build_evo2_regulatory_design_program,
    build_rfdiffusion3_af3_ppi_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.registries import lookup_registry, profile_for_fixture
from protofuse.phillip.topology import recommend_topologies
from protofuse.phillip.workload_preflight import run_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]

_MINIMAL_PDB = """\
ATOM      1  N   ALA A   1      11.104  13.207  10.111  1.00 20.00           N
ATOM      2  CA  ALA A   1      12.000  13.000  10.000  1.00 20.00           C
ATOM      3  C   ALA A   1      12.500  11.600  10.000  1.00 20.00           C
ATOM      4  O   ALA A   1      11.800  10.600  10.000  1.00 20.00           O
TER
END
"""


@pytest.mark.parametrize(
    ("fixture_id", "expected_programs"),
    [
        ("rfdiffusion3-af3-ppi", 6),
        ("af3-boltz2-state-sweep", 51),
        ("evo2-enformer-borzoi", 4),
    ],
)
def test_joint_objective_fixture_compiles_to_safe_sources(
    fixture_id: str,
    expected_programs: int,
) -> None:
    spec = load_fixture_spec(fixture_id)
    profile = profile_for_fixture(fixture_id)
    plan = compile_proto_plan(
        spec,
        recommend_topologies(spec)[0],
        registry=lookup_registry(profile.registry_name),
        device="modal",
    )

    assert plan.executable
    assert plan.topology.value == "multiobjective_search"
    assert len(generate_program_sources(spec, plan, profile=profile)) == expected_programs
    assert spec.global_parameters["paired_full_fused_seed_required"] is True


def test_rfdiffusion3_af3_program_preserves_three_model_objectives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse.phillip import program_builders

    monkeypatch.setattr(
        program_builders,
        "_target_structure_from_pdb",
        lambda _pdb_id: Structure(structure=_MINIMAL_PDB),
    )
    monkeypatch.setattr(
        program_builders,
        "_target_sequence_from_pdb",
        lambda _pdb_id, _chains: "A" * 200,
    )
    monkeypatch.setattr(
        program_builders,
        "crop_target_structure",
        lambda structure, _spans: structure,
    )
    monkeypatch.setattr(
        program_builders,
        "target_sequence_from_cropped_structure",
        lambda _structure, _chains: "A" * 200,
    )
    monkeypatch.setattr(
        program_builders,
        "paper_binder_origin",
        lambda _structure, _hotspots: [0.0, 0.0, 10.0],
    )
    spec = load_fixture_spec("rfdiffusion3-af3-ppi")
    params = resolve_workload_params(spec, tier="smoke")

    program = build_rfdiffusion3_af3_ppi_program(params, target_index=0)
    optimizer = program.optimizers[0]

    assert isinstance(optimizer, RejectionSamplingOptimizer)
    assert optimizer.config.num_samples == 8
    assert optimizer.config.num_results == 4
    assert optimizer.config.seed == 0
    assert {constraint.label for constraint in optimizer.constraints} >= {
        "proteinmpnn_probability",
        "af3_paper_success",
    }
    generator_config = optimizer.generators[0].config
    assert generator_config.rfdiffusion3_config.seed == 0
    assert generator_config.proteinmpnn_config.seed == 0
    assert generator_config.proteinmpnn_config.num_sequences_per_structure == 4


def test_state_sweep_program_has_model_by_state_objective_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse.phillip import program_builders

    monkeypatch.setattr(
        program_builders,
        "_target_structure_from_pdb",
        lambda _pdb_id: Structure(structure=_MINIMAL_PDB),
    )
    monkeypatch.setattr(
        program_builders,
        "_target_sequence_from_pdb",
        lambda _pdb_id, _chains: "A" * 40,
    )
    spec = load_fixture_spec("af3-boltz2-state-sweep")
    params = resolve_workload_params(spec, tier="smoke")

    program = build_af3_boltz2_state_sweep_program(params, seed=3, beta=0.45)
    optimizer = program.optimizers[0]

    assert isinstance(optimizer, RejectionSamplingOptimizer)
    assert optimizer.config.seed == 3
    assert {constraint.label for constraint in optimizer.constraints} >= {
        "alphafold3_scaled_one_minus_tm_dominant",
        "alphafold3_scaled_one_minus_tm_alternative",
        "boltz2_scaled_one_minus_tm_dominant",
        "boltz2_scaled_one_minus_tm_alternative",
    }
    af3_constraints = [
        item for item in optimizer.constraints if item.label.startswith("alphafold3_")
    ]
    boltz_constraints = [
        item for item in optimizer.constraints if item.label.startswith("boltz2_")
    ]
    assert all(item.function_config.seed == 3 for item in af3_constraints)
    assert all(item.function_config.seed == 3 for item in boltz_constraints)
    assert all(item.function_config.beta == 0.45 for item in af3_constraints + boltz_constraints)


def test_pair_scaling_contract_refuses_unscaled_fallback() -> None:
    from protofuse.phillip.pair_scaling_contract import (
        PairScaledStateTMScoreConfig,
        clear_reviewed_pair_scaling_backends,
        install_default_reviewed_pair_scaling_backends,
        pair_scaled_state_tmscore_constraint,
    )

    clear_reviewed_pair_scaling_backends()
    config = PairScaledStateTMScoreConfig(
        model="boltz2",
        beta=-0.15,
        seed=0,
        recycling_steps=3,
        sampling_steps=200,
        diffusion_samples=1,
        step_scale=1.5,
        max_msa_seqs=1024,
        subsample_msa=False,
        target_structure=Structure(structure=_MINIMAL_PDB),
        reference_state="dominant",
    )

    try:
        with pytest.raises(RuntimeError, match="refuses to substitute unscaled"):
            pair_scaled_state_tmscore_constraint(
                [(Sequence(sequence="A", sequence_type="protein"),)],
                config,
            )
    finally:
        install_default_reviewed_pair_scaling_backends()


def test_evo2_program_uses_beam_search_and_separate_predictor_losses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse.phillip import program_builders

    monkeypatch.setattr(
        program_builders,
        "resolve_evo2_genomic_context",
        lambda _payload: ("C" * 163_840, "C" * 40_960, "G" * 359_936),
    )
    spec = load_fixture_spec("evo2-enformer-borzoi")
    params = resolve_workload_params(spec, tier="smoke")

    program = build_evo2_regulatory_design_program(params, morse_pattern=".", dot_bp=128)
    optimizer = program.optimizers[0]

    assert isinstance(optimizer, BeamSearchOptimizer)
    assert optimizer.config.seed == 0
    assert optimizer.config.beam_length == 128
    assert optimizer.config.num_results == 1
    assert optimizer.config.proposals_per_result == 2
    assert optimizer.target_segment.sequence_length == 128
    assert optimizer.config.prompt == "C" * 4096
    assert optimizer.generators[0].config.prompts == ["C" * 4096]
    assert [constraint.label for constraint in optimizer.constraints] == [
        "enformer_pattern_l1_sum",
        "borzoi_pattern_l1_sum",
    ]
    assert [constraint.weight for constraint in optimizer.constraints] == [0.5, 0.5]
    assert "seed" not in type(optimizer.generators[0].config).model_fields


def test_saved_targets_require_paired_full_and_fused_seeds() -> None:
    payload = json.loads(
        (REPO_ROOT / "workspaces/phillip/PAPER_BENCHMARK_TARGETS.json").read_text()
    )

    protocol = payload["paired_full_fused_protocol"]
    assert protocol["required"] is True
    assert protocol["evaluation_seeds"] == [0, 1, 2, 3, 4]
    assert len(payload["workflows"]) == 3
    assert all(workflow["joint_surrogate_objectives"] for workflow in payload["workflows"])


@pytest.mark.parametrize(
    ("fixture_id", "runner_name"),
    [
        ("rfdiffusion3-af3-ppi", "run_rfdiffusion3_af3_ppi"),
        ("af3-boltz2-state-sweep", "run_af3_boltz2_state_sweep"),
        ("evo2-enformer-borzoi", "run_evo2_regulatory_design"),
    ],
)
def test_joint_objective_fixtures_have_cli_run_dispatch(
    fixture_id: str,
    runner_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse import cli
    from protofuse.phillip import program_builders

    sentinel = object()
    monkeypatch.setattr(
        program_builders,
        runner_name,
        lambda *, tier: (sentinel, 12.5),
    )

    program, wall_ms, summary = cli._run_fixture(fixture_id, tier="smoke")

    assert program is sentinel
    assert wall_ms == 12.5
    assert summary is None


@pytest.mark.parametrize(
    "fixture_id",
    [
        "rfdiffusion3-af3-ppi",
        "af3-boltz2-state-sweep",
        "evo2-enformer-borzoi",
    ],
)
def test_joint_objective_preflight_uses_explicit_build_strategy(
    fixture_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse.phillip import program_builders

    monkeypatch.setattr(
        program_builders,
        "_target_structure_from_pdb",
        lambda _pdb_id: Structure(structure=_MINIMAL_PDB),
    )
    monkeypatch.setattr(
        program_builders,
        "_target_sequence_from_pdb",
        lambda _pdb_id, _chains: "A" * 200,
    )
    monkeypatch.setattr(
        program_builders,
        "crop_target_structure",
        lambda structure, _spans: structure,
    )
    monkeypatch.setattr(
        program_builders,
        "target_sequence_from_cropped_structure",
        lambda _structure, _chains: "A" * 200,
    )
    monkeypatch.setattr(
        program_builders,
        "paper_binder_origin",
        lambda _structure, _hotspots: [0.0, 0.0, 10.0],
    )
    monkeypatch.setattr(
        program_builders,
        "resolve_evo2_genomic_context",
        lambda _payload: ("C" * 163_840, "C" * 40_960, "G" * 359_936),
    )

    report = run_preflight(fixture_id)

    assert report.classification == "ok"
    assert report.ladder_steps[0].detail == "build-only preflight (objective execution skipped)"
