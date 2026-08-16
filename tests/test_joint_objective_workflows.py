from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest
from proto_language.core import Program, Sequence
from proto_language.optimizer import RejectionSamplingOptimizer
from proto_tools.entities.structures.structure import Structure

from protofuse.phillip.compiler import compile_proto_plan
from protofuse.phillip.evo2_beam_cache import Evo2PrefixReplayBeamSearchOptimizer
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
        ("evo2-enformer-borzoi", 6),
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


def test_state_sweep_defaults_to_query_only_boltz_and_keeps_af3_optional(
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

    required_program = build_af3_boltz2_state_sweep_program(params, seed=3, beta=0.45)
    optimizer = required_program.optimizers[0]

    assert isinstance(optimizer, RejectionSamplingOptimizer)
    assert optimizer.config.seed == 3
    assert optimizer.config.proposal_batch_size == optimizer.config.num_samples == 1
    assert {constraint.label for constraint in optimizer.constraints} == {
        "boltz2_scaled_one_minus_tm_dominant",
        "boltz2_scaled_one_minus_tm_alternative",
        "length",
    }
    boltz_constraints = [
        item for item in optimizer.constraints if item.label.startswith("boltz2_")
    ]
    assert all(item.function_config.model_seed == 3 for item in boltz_constraints)
    assert all(item.function_config.beta == 0.45 for item in boltz_constraints)
    assert all(not item.function_config.use_msa for item in boltz_constraints)

    optional_program = build_af3_boltz2_state_sweep_program(
        params,
        seed=3,
        beta=0.45,
        models=("alphafold3", "boltz2"),
    )
    optional_labels = {
        constraint.label for constraint in optional_program.optimizers[0].constraints
    }
    assert optional_labels >= {
        "alphafold3_scaled_one_minus_tm_dominant",
        "alphafold3_scaled_one_minus_tm_alternative",
        "boltz2_scaled_one_minus_tm_dominant",
        "boltz2_scaled_one_minus_tm_alternative",
    }


@pytest.mark.parametrize(
    ("tier", "expected_samples", "expected_diffusion_samples"),
    [("smoke", 1, 1), ("full", 5, 5)],
)
def test_state_sweep_scores_all_draws_in_one_proposal_batch(
    tier: Literal["smoke", "full"],
    expected_samples: int,
    expected_diffusion_samples: int,
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
    params = resolve_workload_params(spec, tier=tier)

    program = build_af3_boltz2_state_sweep_program(
        params,
        seed=0,
        beta=-0.15,
        models=("boltz2",),
    )
    optimizer = program.optimizers[0]

    assert isinstance(optimizer, RejectionSamplingOptimizer)
    assert optimizer.config.num_samples == expected_samples
    assert optimizer.config.proposal_batch_size == expected_samples
    model_constraints = [
        constraint
        for constraint in optimizer.constraints
        if constraint.label.startswith("boltz2_")
    ]
    assert all(
        constraint.function_config.diffusion_samples == expected_diffusion_samples
        for constraint in model_constraints
    )
    assert all(not constraint.function_config.use_msa for constraint in model_constraints)


def test_state_sweep_reuses_each_fixed_seed_batch_for_both_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from proto_tools import USalignInput

    from protofuse.phillip import pair_scaling_contract, program_builders
    from protofuse.phillip.pair_scaling_contract import PairScalingBackendRequest

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

    aligned_sources: list[str | None] = []

    def fake_usalign(input_data: USalignInput, _config: object) -> object:
        query = input_data.query_structure
        aligned_sources.append(query.source)
        return SimpleNamespace(
            metrics={
                "tm_score_structure_1": 0.5,
                "tm_score_structure_2": 0.5,
            }
        )

    monkeypatch.setattr(pair_scaling_contract, "run_usalign", fake_usalign)

    calls: list[tuple[str, list[str], PairScalingBackendRequest]] = []

    def fake_backend(
        sequences: list[str], request: PairScalingBackendRequest
    ) -> list[Structure]:
        call_number = len(calls)
        calls.append((request.model, list(sequences), request))
        return [
            Structure(
                structure=_MINIMAL_PDB,
                source=f"{request.model}-call-{call_number}-sample-{sample_index}",
            )
            for sample_index in range(len(sequences))
        ]

    pair_scaling_contract.clear_reviewed_pair_scaling_backends()
    pair_scaling_contract.register_reviewed_pair_scaling_backend("boltz2", fake_backend)
    try:
        spec = load_fixture_spec("af3-boltz2-state-sweep")
        params = resolve_workload_params(spec, tier="full")
        program = build_af3_boltz2_state_sweep_program(
            params,
            seed=0,
            beta=-0.15,
        )

        optimizer = program.optimizers[0]
        optimizer.run()
    finally:
        pair_scaling_contract.install_default_reviewed_pair_scaling_backends()

    assert [
        (
            model,
            len(sequences),
            len(set(sequences)),
            request.model_seed,
            request.diffusion_samples,
        )
        for model, sequences, request in calls
    ] == [
        ("boltz2", 5, 1, 0, 5),
    ]
    assert aligned_sources[:5] == aligned_sources[5:10]


def test_paired_state_sweep_does_not_reuse_predictions_across_arms_or_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from proto_tools import USalignInput

    from protofuse.phillip import pair_scaling_contract, program_builders
    from protofuse.phillip.pair_scaling_contract import PairScalingBackendRequest
    from protofuse.sai.evaluation import evaluate_paired_transform

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

    aligned_sources: list[str | None] = []

    def fake_usalign(input_data: USalignInput, _config: object) -> object:
        aligned_sources.append(input_data.query_structure.source)
        return SimpleNamespace(
            metrics={
                "tm_score_structure_1": 0.5,
                "tm_score_structure_2": 0.5,
            }
        )

    monkeypatch.setattr(pair_scaling_contract, "run_usalign", fake_usalign)

    calls: list[PairScalingBackendRequest] = []

    def fake_backend(
        sequences: list[str], request: PairScalingBackendRequest
    ) -> list[Structure]:
        call_number = len(calls)
        calls.append(request)
        return [
            Structure(
                structure=_MINIMAL_PDB,
                source=f"call-{call_number}",
            )
            for _sequence in sequences
        ]

    pair_scaling_contract.clear_reviewed_pair_scaling_backends()
    pair_scaling_contract.register_reviewed_pair_scaling_backend("boltz2", fake_backend)
    try:
        spec = load_fixture_spec("af3-boltz2-state-sweep")
        params = resolve_workload_params(spec, tier="smoke")

        def build_program() -> Program:
            return build_af3_boltz2_state_sweep_program(
                params,
                seed=0,
                beta=-0.15,
                models=("boltz2",),
            )

        evaluation = evaluate_paired_transform(
            build_program,
            lambda program: program,
            optimizer_index=0,
            seeds=(11, 12),
            warmup=False,
        )
    finally:
        pair_scaling_contract.install_default_reviewed_pair_scaling_backends()

    assert [run.status for run in evaluation.runs] == ["ok", "ok"]
    assert len(calls) == 4
    assert aligned_sources == [
        "call-0",
        "call-0",
        "call-1",
        "call-1",
        "call-2",
        "call-2",
        "call-3",
        "call-3",
    ]


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
        model_seed=0,
        recycling_steps=3,
        sampling_steps=200,
        diffusion_samples=1,
        step_scale=1.5,
        use_msa=True,
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

    assert isinstance(optimizer, Evo2PrefixReplayBeamSearchOptimizer)
    assert optimizer.config.seed == 0
    assert optimizer.config.beam_length == 128
    assert optimizer.config.num_results == 1
    assert optimizer.config.proposals_per_result == 2
    assert optimizer.target_segment.sequence_length == 128
    assert optimizer.config.prompt == "C" * 4096
    assert optimizer.config.use_kv_caching is True
    assert optimizer.generators[0].config.prompts == ["C" * 4096]
    assert optimizer.generators[0].force_prompt_threshold == 3000
    assert optimizer.generators[0].store_kv_cache is False
    assert optimizer.generators[0].stop_at_eos is False
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
