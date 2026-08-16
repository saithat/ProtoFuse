from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from proto_language.core import Constraint, ConstraintOutput, Construct, Program, Segment
from proto_language.optimizer import RejectionSamplingOptimizer, RejectionSamplingOptimizerConfig

from protofuse.sai import evaluation as evaluation_module
from protofuse.sai.analyzer import load_reviewed_program
from protofuse.sai.artifacts import (
    FusionManifest,
    load_fusion_artifact,
    write_unreviewed_fusion_artifact,
)
from protofuse.sai.evaluation import ProgramOutputs, classify_proto_energy, evaluate_paired
from protofuse.sai.model import LinearEnsembleModel, SequenceFeatureSchema
from protofuse.sai.profiling import profile_traces
from protofuse.sai.registry import FusionRegistry
from protofuse.sai.router import SurrogatePrediction
from protofuse.sai.signatures import program_signature, step_group_signature
from protofuse.sai.tracing import JsonlTraceWriter, TraceRow, trace_program_constraints
from protofuse.sai.training import (
    load_teacher_samples,
    train_linear_ensemble,
    write_trained_fusion,
)
from protofuse.sai.transform import FusionCompatibilityError, transform_with_artifact

REPO_ROOT = Path(__file__).resolve().parents[1]
DNACHISEL_COLLECTION = REPO_ROOT / "proto_programs/generated/dnachisel-num1"


def objective_low(
    inputs: list[tuple[Any, ...]],
    config: dict[str, Any] | None,
) -> list[ConstraintOutput]:
    del config
    return [ConstraintOutput(score=0.25, metadata={"teacher": "low"}) for _ in inputs]


def objective_high(
    inputs: list[tuple[Any, ...]],
    config: dict[str, Any] | None,
) -> list[ConstraintOutput]:
    del config
    return [ConstraintOutput(score=0.75, metadata={"teacher": "high"}) for _ in inputs]


def build_constant_program() -> Program:
    segment = Segment(sequence="ACGT", sequence_type="dna", label="target")
    construct = Construct([segment])
    constraints = [
        Constraint(inputs=[segment], function=objective_low, label="low", weight=1.0),
        Constraint(inputs=[segment], function=objective_high, label="high", weight=1.0),
    ]
    optimizer = RejectionSamplingOptimizer(
        constructs=[construct],
        generators=[],
        constraints=constraints,
        config=RejectionSamplingOptimizerConfig(
            num_samples=1,
            num_results=1,
            proposal_source="existing_results",
        ),
    )
    return Program(optimizers=[optimizer], num_results=1, seed=17)


def constant_model(*, support_threshold: float = 10.0) -> LinearEnsembleModel:
    schema = SequenceFeatureSchema(
        sequence_type="dna",
        alphabet="ACGT",
        kmer_size=1,
        include_composition=False,
        expected_length=4,
    )
    matrix = (
        (0.25, 0.75),
        (0.0, 0.0),
        (0.0, 0.0),
        (0.0, 0.0),
        (0.0, 0.0),
    )
    return LinearEnsembleModel(
        input_schemas=(schema,),
        output_labels=("low", "high"),
        coefficients=(matrix, matrix),
        feature_center=(0.0, 0.0, 0.0, 0.0),
        feature_scale=(1.0, 1.0, 1.0, 1.0),
        support_threshold=support_threshold,
        uncertainty_threshold=0.0,
        calibration_absolute_error=(0.0, 0.0),
    )


def write_artifact(
    root: Path,
    *,
    reviewed: bool,
    support_threshold: float = 10.0,
) -> Any:
    program = build_constant_program()
    signature = step_group_signature(
        program,
        optimizer_index=0,
        constraint_labels=("low", "high"),
    )
    manifest = FusionManifest(
        fusion_id="constant-objectives",
        version="1",
        optimizer_index=0,
        constraint_labels=("low", "high"),
        group_signature=signature,
        group_signature_sha256=signature.sha256,
        model_sha256="0" * 64,
    )
    artifact = write_unreviewed_fusion_artifact(
        root,
        manifest=manifest,
        model=constant_model(support_threshold=support_threshold),
    )
    if reviewed:
        reviewed_manifest = artifact.manifest.model_copy(update={"reviewed": True})
        (root / "manifest.json").write_text(reviewed_manifest.model_dump_json(indent=2) + "\n")
    return load_fusion_artifact(root, require_reviewed=reviewed)


def test_reviewed_analyzer_builds_real_program_and_signature_is_stable() -> None:
    first = load_reviewed_program(DNACHISEL_COLLECTION, program_id="design-002")
    second = load_reviewed_program(DNACHISEL_COLLECTION, program_id="design-002")

    assert first.entry.path == "design_002.py"
    assert first.signature.sha256 == second.signature.sha256
    assert first.signature == program_signature(first.program)
    assert first.signature.optimizers[0].constraints


def test_artifact_loader_requires_review_and_verifies_hash(tmp_path: Path) -> None:
    artifact = write_artifact(tmp_path / "artifact", reviewed=False)

    assert artifact.manifest.reviewed is False
    with pytest.raises(ValueError, match="not reviewed"):
        load_fusion_artifact(artifact.root)
    (artifact.root / "model.json").write_text("{}\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_fusion_artifact(artifact.root, require_reviewed=False)


def test_transform_is_transactional_and_runs_surrogate_with_parent_validation(
    tmp_path: Path,
) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)
    original = build_constant_program()
    fused = transform_with_artifact(original, artifact)

    assert len(original.optimizers) == 1
    assert [constraint.label for constraint in original.optimizers[0].constraints] == [
        "low",
        "high",
    ]
    assert len(fused.optimizers) == 2

    original.run()
    fused.run()

    assert original.constructs[0].joined_sequences[0].sequence == "ACGT"
    assert fused.constructs[0].joined_sequences[0].sequence == "ACGT"
    assert original.energy_scores == pytest.approx([1.0])
    assert fused.energy_scores == pytest.approx([1.0])
    evaluator = cast(Any, fused)._protofuse_evaluators[0]
    assert evaluator.routing_counts == {"surrogate": 1, "full_model": 0}


def test_transform_routes_ood_inputs_to_complete_parent_group(tmp_path: Path) -> None:
    artifact = write_artifact(
        tmp_path / "reviewed",
        reviewed=True,
        support_threshold=0.0,
    )
    fused = transform_with_artifact(build_constant_program(), artifact)

    fused.run()

    evaluator = cast(Any, fused)._protofuse_evaluators[0]
    assert evaluator.routing_counts == {"surrogate": 0, "full_model": 1}
    assert fused.energy_scores == pytest.approx([1.0])


def test_transform_rejects_signature_drift_without_mutating_program(tmp_path: Path) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)
    changed = build_constant_program()
    changed.optimizers[0].constraints[0]._weight = 0.5

    with pytest.raises(FusionCompatibilityError, match="signature"):
        transform_with_artifact(changed, artifact)

    assert len(changed.optimizers) == 1
    assert changed.optimizers[0].constraints[0].function is objective_low


def test_runtime_discovers_reviewed_artifacts_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse import runtime

    model_root = tmp_path / "models"
    write_artifact(model_root / "constant", reviewed=True)
    monkeypatch.setattr(runtime, "_DEFAULT_REGISTRY", FusionRegistry[Any]())
    monkeypatch.setattr(runtime, "_DISCOVERY_ATTEMPTED", False)
    monkeypatch.setattr(runtime, "_DISCOVERY_DIAGNOSTICS", [])

    first = runtime.discover_fusions(model_root)
    second = runtime.discover_fusions(model_root)
    result = runtime.optimize_with_report(build_constant_program())

    assert first == ("constant-objectives@1",)
    assert second == ()
    assert result.applied_fusions == ("constant-objectives@1",)
    assert len(result.program.optimizers) == 2


def test_trace_training_and_unreviewed_packaging_are_reproducible(tmp_path: Path) -> None:
    trace_path = tmp_path / "teacher.jsonl"
    program = build_constant_program()
    with trace_program_constraints(
        program,
        JsonlTraceWriter(trace_path),
        run_id="run-0",
        group_id="group-0",
    ):
        program.run()
    assert program.optimizers[0].constraints[0].function is objective_low
    traced_rows = [
        TraceRow.model_validate_json(line) for line in trace_path.read_text().splitlines()
    ]
    assert {row.constraint_label for row in traced_rows} == {"low", "high"}
    profile = profile_traces((trace_path,))
    assert [(item.calls, item.proposals) for item in profile.constraints] == [(1, 1), (1, 1)]

    rows: list[dict[str, Any]] = []
    for group_index, sequence in enumerate(("AAAA", "CCCC", "GGGG")):
        for label, score in (("low", 0.25), ("high", 0.75)):
            rows.append(
                TraceRow(
                    recorded_at="2026-08-15T00:00:00+00:00",
                    run_id=f"run-{group_index}",
                    group_id=f"group-{group_index}",
                    program_sha256="0" * 64,
                    optimizer_index=0,
                    constraint_label=label,
                    constraint_identity=f"tests.{label}",
                    call_index=group_index,
                    proposal_index=0,
                    input_sha256=(f"hash-{group_index}",),
                    input_sequences=(sequence,),
                    input_structure_sha256=(None,),
                    score=score,
                    metadata={},
                    has_structures=False,
                    has_logits=False,
                    call_latency_seconds=0.01,
                ).model_dump(mode="json")
            )
    training_trace = tmp_path / "training.jsonl"
    training_trace.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    samples = load_teacher_samples(
        (training_trace,),
        optimizer_index=0,
        constraint_labels=("low", "high"),
    )
    result = train_linear_ensemble(
        samples,
        output_labels=("low", "high"),
        trace_paths=(training_trace,),
        seed=5,
        ensemble_size=2,
    )
    packaged = write_trained_fusion(
        tmp_path / "trained",
        program=build_constant_program(),
        optimizer_index=0,
        constraint_labels=("low", "high"),
        fusion_id="trained-constant",
        version="1",
        result=result,
    )

    assert len(samples) == 3
    assert packaged.manifest.reviewed is False
    assert result.split.train_samples == 1
    assert result.metrics["audit_rank_correlation"] == [None, None]
    assert result.metrics["audit_score_q95_q05_range"] == [0.0, 0.0]
    assert result.metrics["audit_accepted_mae_q95_q05_fraction"] == [None, None]
    assert (packaged.root / "split.json").is_file()
    assert (packaged.root / "metrics.json").is_file()


def test_paired_evaluation_excludes_warmup_and_reports_complete_metrics(tmp_path: Path) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)
    progress_counts: list[int] = []

    evaluation = evaluate_paired(
        build_constant_program,
        artifact,
        seeds=(11, 12),
        offline_surrogate_metrics={
            "audit_mae": [0.0, 0.0],
            "audit_accepted_mae_q95_q05_fraction": [0.04, 0.03],
        },
        on_progress=lambda partial: progress_counts.append(len(partial.runs)),
    )
    payload = evaluation.as_dict()

    assert evaluation.warmup is not None
    assert evaluation.warmup.excluded_from_primary_timing is True
    assert [run.order for run in evaluation.runs] == [
        ("full", "fused"),
        ("fused", "full"),
    ]
    assert payload["protocol"]["cold_start_in_primary_timing"] is False
    assert payload["metrics"]["reliability"]["fully_valid_accuracy_runs"] == 2
    assert payload["metrics"]["routing"]["surrogate_coverage"] == pytest.approx(1.0)
    assert (
        payload["metrics"]["routing"][
            "initial_stage_target_parent_item_evaluations_bypassed"
        ]
        == 4
    )
    assert (
        payload["metrics"]["routing"]["mandatory_final_validation_parent_item_evaluations"]
        == 4
    )
    assert payload["metrics"]["routing"]["net_parent_item_evaluations_avoided"] == 0
    # Kept only as an explicitly scoped alias for pre-existing report consumers.
    assert payload["metrics"]["routing"]["target_parent_item_evaluations_avoided"] == 4
    assert "initial routing stage only" in payload["metrics"]["routing"][
        "target_parent_item_evaluations_avoided_scope"
    ]
    assert payload["metrics"]["routing"]["deferral_reasons"] == {
        "calibrated_in_domain": 2
    }
    full_metadata = payload["runs"][0]["full_result_metadata"][0]
    assert full_metadata["segments"]["target"]["constraints"]["low"]["data"] == {
        "teacher": "low"
    }
    assert payload["metrics"]["accuracy"]["accepted_mae_q95_q05_fraction"] == [0.04, 0.03]
    assert payload["offline_surrogate_metrics"] == {
        "audit_mae": [0.0, 0.0],
        "audit_accepted_mae_q95_q05_fraction": [0.04, 0.03],
    }
    assert progress_counts == [1, 2]
    json.dumps(payload, allow_nan=False)


def test_paired_evaluation_subtracts_final_validation_from_parent_work(
    tmp_path: Path,
) -> None:
    artifact = write_artifact(
        tmp_path / "reviewed",
        reviewed=True,
        support_threshold=0.0,
    )

    payload = evaluate_paired(
        build_constant_program,
        artifact,
        seeds=(11,),
        warmup=False,
    ).as_dict()
    run = payload["runs"][0]
    routing = payload["metrics"]["routing"]

    assert run["initial_stage_parent_item_evaluations_bypassed"] == 0
    assert run["parent_item_evaluations_from_fallback"] == 2
    assert run["mandatory_final_validation_parent_item_evaluations"] == 2
    assert run["net_parent_item_evaluations_avoided"] == -2
    assert routing["initial_stage_target_parent_item_evaluations_bypassed"] == 0
    assert routing["target_parent_item_evaluations_from_fallback"] == 2
    assert routing["mandatory_final_validation_parent_item_evaluations"] == 2
    assert routing["net_parent_item_evaluations_avoided"] == -2


def test_paired_evaluation_does_not_compare_pool_relative_energies(tmp_path: Path) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)

    def build_pool_relative_program() -> Program:
        program = build_constant_program()
        program.optimizers[0].pool_relative_objective = True
        program.optimizers[0].candidate_pool_sha256 = "a" * 64
        program.optimizers[0].candidate_pool_size = 1
        return program

    payload = evaluate_paired(
        build_pool_relative_program,
        artifact,
        seeds=(11,),
        warmup=False,
    ).as_dict()
    run = payload["runs"][0]

    assert run["energy_comparable"] is False
    assert run["candidate_pool_identical"] is True
    assert run["full_candidate_pool_sha256"] == "a" * 64
    assert run["full_candidate_pool_size"] == 1
    assert run["finite_energy_differences"] == ()
    assert run["best_energy_regret"] is None
    assert run["top_k_recall"] == pytest.approx(1.0)
    assert payload["metrics"]["accuracy"]["energy_comparable_runs"] == 0
    assert payload["metrics"]["accuracy"]["final_energy_mae"] is None


def test_paired_evaluation_rejects_mismatched_pool_relative_candidates(
    tmp_path: Path,
) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)
    builds = 0

    def build_mismatched_pool_program() -> Program:
        nonlocal builds
        program = build_constant_program()
        program.optimizers[0].pool_relative_objective = True
        program.optimizers[0].candidate_pool_sha256 = ("a" if builds == 0 else "b") * 64
        program.optimizers[0].candidate_pool_size = 1
        builds += 1
        return program

    payload = evaluate_paired(
        build_mismatched_pool_program,
        artifact,
        seeds=(11,),
        warmup=False,
    ).as_dict()

    assert payload["runs"][0]["status"] == "candidate_pool_mismatch"
    assert payload["runs"][0]["candidate_pool_identical"] is False
    assert payload["runs"][0]["speedup"] is None
    assert payload["metrics"]["reliability"]["candidate_pool_mismatches"] == 1


def test_fusion_gate_defers_non_finite_support_and_uncertainty(tmp_path: Path) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)
    fused = transform_with_artifact(build_constant_program(), artifact)
    evaluator = cast(Any, fused)._protofuse_evaluators[0]

    invalid_support = evaluator._gate(
        (),
        SurrogatePrediction(
            (),
            {"values": (0.25, 0.75), "uncertainties": (0.0, 0.0), "support_score": float("nan")},
        ),
    )
    invalid_uncertainty = evaluator._gate(
        (),
        SurrogatePrediction(
            (),
            {"values": (0.25, 0.75), "uncertainties": (0.0, float("nan")), "support_score": 0.0},
        ),
    )

    assert (invalid_support.use_surrogate, invalid_support.reason) == (
        False,
        "invalid_support_score",
    )
    assert (invalid_uncertainty.use_surrogate, invalid_uncertainty.reason) == (
        False,
        "invalid_uncertainty",
    )


def test_proto_energy_classification_matches_proto_sentinels() -> None:
    assert classify_proto_energy(0.5) == "finite"
    assert classify_proto_energy(float("nan")) == "nan"
    assert classify_proto_energy(float("inf")) == "positive_infinity"
    assert classify_proto_energy(float("-inf")) == "negative_infinity"


def test_paired_evaluation_reports_non_finite_final_energy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = write_artifact(tmp_path / "reviewed", reviewed=True)
    original_outputs = evaluation_module._outputs

    def non_finite_outputs(
        program: Program, *, optimizer_index: int
    ) -> ProgramOutputs:
        outputs = original_outputs(program, optimizer_index=optimizer_index)
        return ProgramOutputs(outputs.sequences, (float("inf"),))

    monkeypatch.setattr(evaluation_module, "_outputs", non_finite_outputs)
    payload = evaluate_paired(
        build_constant_program,
        artifact,
        seeds=(1,),
        warmup=False,
    ).as_dict()

    assert payload["runs"][0]["status"] == "non_finite_energy"
    assert payload["runs"][0]["full_energy_kinds"] == ("positive_infinity",)
    assert payload["runs"][0]["full_energies"] == (None,)
    assert payload["metrics"]["reliability"]["non_finite_energy_runs"] == 1
    assert payload["metrics"]["accuracy"]["final_energy_mae"] is None
    assert payload["metrics"]["accuracy"]["all_final_sequences_identical"] is None
    json.dumps(payload, allow_nan=False)
