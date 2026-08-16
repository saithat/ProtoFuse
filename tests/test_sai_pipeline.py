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
from protofuse.sai.model import (
    BORZOI_LCB_MAXIMUM_L1_PER_BIN,
    LinearEnsembleModel,
    LinearEnsemblePredictor,
    OutputNormalization,
    SequenceFeatureSchema,
    evo2_output_normalizations,
    featurize_inputs,
)
from protofuse.sai.profiling import profile_traces
from protofuse.sai.registry import FusionRegistry
from protofuse.sai.router import SurrogatePrediction
from protofuse.sai.signatures import program_signature, step_group_signature
from protofuse.sai.tracing import JsonlTraceWriter, TraceRow, trace_program_constraints
from protofuse.sai.training import (
    TeacherSample,
    infer_feature_schemas,
    load_teacher_samples,
    train_linear_ensemble,
    validate_teacher_trace_contract,
    write_trained_fusion,
)
from protofuse.sai.transform import (
    FusionCompatibilityError,
    linear_gate_decision,
    transform_with_artifact,
)

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


def raw_enformer_l1(
    inputs: list[tuple[Any, ...]],
    config: dict[str, Any] | None,
) -> list[ConstraintOutput]:
    del config
    return [
        ConstraintOutput(score=0.25 * ((len(item[1].sequence) + 127) // 128))
        for item in inputs
    ]


def raw_borzoi_l1(
    inputs: list[tuple[Any, ...]],
    config: dict[str, Any] | None,
) -> list[ConstraintOutput]:
    del config
    return [
        ConstraintOutput(
            score=(
                0.50
                * ((len(item[1].sequence) + 31) // 32)
                * BORZOI_LCB_MAXIMUM_L1_PER_BIN
            )
        )
        for item in inputs
    ]


raw_enformer_l1._constraint_allow_raw_scores = True  # type: ignore[attr-defined]
raw_borzoi_l1._constraint_allow_raw_scores = True  # type: ignore[attr-defined]


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


def build_raw_l1_program(*, target_bp: int = 128) -> Program:
    left = Segment(sequence="C", sequence_type="dna", label="Left Flank")
    target = Segment(sequence="A" * target_bp, sequence_type="dna", label="Target")
    right = Segment(sequence="C", sequence_type="dna", label="Right Flank")
    inputs = [left, target, right]
    optimizer = RejectionSamplingOptimizer(
        constructs=[Construct(inputs)],
        generators=[],
        constraints=[
            Constraint(
                inputs=inputs,
                function=raw_enformer_l1,
                label="enformer_pattern_l1_sum",
                weight=0.5,
            ),
            Constraint(
                inputs=inputs,
                function=raw_borzoi_l1,
                label="borzoi_pattern_l1_sum",
                weight=0.5,
            ),
        ],
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


def test_legacy_model_defaults_to_identity_output_normalization() -> None:
    payload = constant_model().model_dump(mode="json")
    payload.pop("output_normalizations")
    payload["input_schemas"][0].pop("position_encoding")
    payload["schema_version"] = "1.0"

    model = LinearEnsembleModel.model_validate(payload)
    prediction = LinearEnsemblePredictor(model).predict(("ACGT",))

    assert model.resolved_output_normalizations == (
        OutputNormalization(),
        OutputNormalization(),
    )
    assert prediction.values == pytest.approx((0.25, 0.75))
    assert prediction.normalized_values == pytest.approx((0.25, 0.75))
    assert linear_gate_decision(
        model,
        values=prediction.normalized_values,
        uncertainties=prediction.normalized_uncertainties,
        support_score=0.0,
    ).use_surrogate
    assert linear_gate_decision(
        model,
        values=(0.25, 1.01),
        uncertainties=(0.0, 0.0),
        support_score=0.0,
    ).reason == "prediction_out_of_range"


def test_position_encoding_is_order_sensitive_and_backward_compatible() -> None:
    aggregate = SequenceFeatureSchema(
        sequence_type="protein",
        alphabet="AC",
        kmer_size=1,
        include_composition=False,
        expected_length=2,
    )
    positional = aggregate.model_copy(update={"position_encoding": "one_hot"})

    aggregate_ac = featurize_inputs(("AC",), (aggregate,))
    aggregate_ca = featurize_inputs(("CA",), (aggregate,))
    positional_ac = featurize_inputs(("AC",), (positional,))
    positional_ca = featurize_inputs(("CA",), (positional,))

    assert aggregate_ac == aggregate_ca == pytest.approx((0.5, 0.5))
    assert positional.feature_count == 6
    assert positional_ac == pytest.approx((0.5, 0.5, 1.0, 0.0, 0.0, 1.0))
    assert positional_ca == pytest.approx((0.5, 0.5, 0.0, 1.0, 1.0, 0.0))


def test_position_encoding_requires_fixed_length() -> None:
    with pytest.raises(ValueError, match="requires expected_length"):
        SequenceFeatureSchema(
            sequence_type="protein",
            alphabet="AC",
            include_composition=False,
            position_encoding="one_hot",
        )


def test_fixed_length_protein_schema_infers_position_encoding() -> None:
    fixed_protein = (
        TeacherSample(sequences=("MK",), outputs=(0.1,), group_id="a"),
        TeacherSample(sequences=("MR",), outputs=(0.2,), group_id="b"),
    )
    variable_protein = (
        TeacherSample(sequences=("MK",), outputs=(0.1,), group_id="a"),
        TeacherSample(sequences=("MKR",), outputs=(0.2,), group_id="b"),
    )
    fixed_dna = (
        TeacherSample(sequences=("ACG",), outputs=(0.1,), group_id="a"),
        TeacherSample(sequences=("TGC",), outputs=(0.2,), group_id="b"),
    )

    protein_schema = infer_feature_schemas(fixed_protein)[0]
    variable_schema = infer_feature_schemas(variable_protein)[0]
    dna_schema = infer_feature_schemas(fixed_dna)[0]

    assert protein_schema.position_encoding == "one_hot"
    assert protein_schema.include_composition is False
    assert variable_schema.position_encoding == "none"
    assert dna_schema.position_encoding == "none"

    with pytest.raises(ValueError, match="does not match expected"):
        featurize_inputs(("MKR",), (protein_schema,))


def test_fixed_length_protein_training_round_trips_positional_model(
    tmp_path: Path,
) -> None:
    samples = tuple(
        TeacherSample(
            sequences=(sequence,),
            outputs=outputs,
            group_id=f"protein-{index}",
        )
        for index, (sequence, outputs) in enumerate(
            (
                ("MK", (0.10, 0.80)),
                ("MR", (0.20, 0.70)),
                ("AK", (0.30, 0.60)),
                ("AR", (0.40, 0.50)),
                ("DK", (0.50, 0.40)),
            )
        )
    )
    trace_path = tmp_path / "protein-training.jsonl"
    trace_path.write_text("synthetic fixed-protein cohort\n")

    result = train_linear_ensemble(
        samples,
        output_labels=("sequence_family", "structure_family"),
        trace_paths=(trace_path,),
        seed=3,
        ensemble_size=2,
    )
    reloaded = LinearEnsembleModel.model_validate_json(result.model.model_dump_json())
    prediction = LinearEnsemblePredictor(reloaded).predict(("MR",))

    [schema] = reloaded.input_schemas
    assert schema.position_encoding == "one_hot"
    assert schema.feature_count == 60
    assert all(len(member) == 61 for member in reloaded.coefficients)
    assert all(len(row) == 2 for member in reloaded.coefficients for row in member)
    assert len(prediction.values) == len(prediction.uncertainties) == 2


def test_sequence_bin_normalization_uses_target_length_and_ceiling() -> None:
    normalization = OutputNormalization(
        kind="sequence_bins",
        input_index=1,
        resolution_bp=128,
        trim_prefix_bp=128,
        maximum_loss_per_bin=1.25,
    )
    sequences = ("C" * 16, "A" * 257, "G" * 16)

    assert normalization.sequence_bin_count(sequences) == 2
    assert normalization.scale(sequences) == pytest.approx(2.5)
    with pytest.raises(ValueError, match="empty after prefix"):
        normalization.scale(("C", "A" * 128, "G"))

    enformer, borzoi = evo2_output_normalizations(
        ("enformer_pattern_l1_sum", "borzoi_pattern_l1_sum")
    )
    final_sequences = ("C", "A" * 19_968, "G")
    assert enformer.sequence_bin_count(final_sequences) == 156
    assert borzoi.sequence_bin_count(final_sequences) == 624
    with pytest.raises(ValueError, match="maximum is 156"):
        enformer.scale(("C", "A" * 20_096, "G"))


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


def test_transform_decodes_raw_l1_scores_before_proto_energy(tmp_path: Path) -> None:
    labels = ("enformer_pattern_l1_sum", "borzoi_pattern_l1_sum")
    program = build_raw_l1_program()
    signature = step_group_signature(
        program,
        optimizer_index=0,
        constraint_labels=labels,
    )
    schema = SequenceFeatureSchema(
        sequence_type="dna",
        alphabet="AC",
        kmer_size=1,
        include_composition=False,
    )
    matrix = ((0.25, 0.50), *((0.0, 0.0),) * 6)
    model = LinearEnsembleModel(
        input_schemas=(schema, schema, schema),
        output_labels=labels,
        output_normalizations=evo2_output_normalizations(labels),
        coefficients=(matrix, matrix),
        feature_center=(0.0, 1.0, 1.0, 0.0, 0.0, 1.0),
        feature_scale=(1.0,) * 6,
        support_threshold=0.0,
        uncertainty_threshold=0.0,
        calibration_absolute_error=(0.0, 0.0),
    )
    manifest = FusionManifest(
        fusion_id="raw-l1-objectives",
        version="1",
        optimizer_index=0,
        constraint_labels=labels,
        group_signature=signature,
        group_signature_sha256=signature.sha256,
        model_sha256="0" * 64,
    )
    artifact = write_unreviewed_fusion_artifact(
        tmp_path / "raw-l1",
        manifest=manifest,
        model=model,
    )
    reviewed = artifact.manifest.model_copy(update={"reviewed": True})
    (artifact.root / "manifest.json").write_text(reviewed.model_dump_json(indent=2) + "\n")
    artifact = load_fusion_artifact(artifact.root)

    original = build_raw_l1_program()
    fused = transform_with_artifact(build_raw_l1_program(), artifact)
    original.run()
    fused.run()

    expected_energy = 0.5 * (0.25 + 2.0 * BORZOI_LCB_MAXIMUM_L1_PER_BIN)
    assert expected_energy > 1.0
    assert original.energy_scores == pytest.approx([expected_energy])
    assert fused.energy_scores == pytest.approx([expected_energy])
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

    incomplete_trace = tmp_path / "training-incomplete.jsonl"
    incomplete_trace.write_text(
        "\n".join(json.dumps(row) for row in rows[:-1]) + "\n"
    )
    with pytest.raises(ValueError, match="objective group is incomplete"):
        load_teacher_samples(
            (incomplete_trace,),
            optimizer_index=0,
            constraint_labels=("low", "high"),
        )

    mixed_rows = [dict(row) for row in rows]
    mixed_rows[1]["program_sha256"] = "1" * 64
    mixed_trace = tmp_path / "training-mixed.jsonl"
    mixed_trace.write_text("\n".join(json.dumps(row) for row in mixed_rows) + "\n")
    with pytest.raises(ValueError, match="disagree on trace provenance"):
        load_teacher_samples(
            (mixed_trace,),
            optimizer_index=0,
            constraint_labels=("low", "high"),
        )

    failed_rows = [dict(row) for row in rows]
    failed_rows[0]["score"] = None
    failed_rows[0]["error"] = "RuntimeError:teacher failed"
    failed_trace = tmp_path / "training-failed.jsonl"
    failed_trace.write_text("\n".join(json.dumps(row) for row in failed_rows) + "\n")
    with pytest.raises(ValueError, match="failed or incomplete row"):
        load_teacher_samples(
            (failed_trace,),
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


def test_sequence_bin_training_decodes_varying_raw_l1_sums(tmp_path: Path) -> None:
    labels = ("enformer_pattern_l1_sum", "borzoi_pattern_l1_sum")
    normalizations = evo2_output_normalizations(labels)
    samples = tuple(
        TeacherSample(
            sequences=("C" * 16, "A" * target_bp, "G" * 16),
            outputs=(
                0.25 * (target_bp // 128),
                0.50
                * (target_bp // 32)
                * BORZOI_LCB_MAXIMUM_L1_PER_BIN,
            ),
            group_id=f"stage-{target_bp}",
            output_target_bins=(target_bp // 128, target_bp // 32),
        )
        for target_bp in (128, 256, 384)
    )
    trace_path = tmp_path / "raw-l1-trace.jsonl"
    trace_path.write_text("synthetic raw-score provenance\n")

    result = train_linear_ensemble(
        samples,
        output_labels=labels,
        output_normalizations=normalizations,
        trace_paths=(trace_path,),
        seed=5,
        ensemble_size=2,
    )
    model = LinearEnsembleModel.model_validate_json(result.model.model_dump_json())
    prediction = LinearEnsemblePredictor(model).predict(
        ("C" * 16, "A" * 512, "G" * 16)
    )

    assert prediction.normalized_values == pytest.approx((0.25, 0.50))
    assert prediction.values == pytest.approx(
        (1.0, 8.0 * BORZOI_LCB_MAXIMUM_L1_PER_BIN)
    )
    assert prediction.normalized_uncertainties == pytest.approx((0.0, 0.0))
    assert result.metrics["audit_score_q95"][1] > 1.0
    assert linear_gate_decision(
        model,
        values=prediction.normalized_values,
        uncertainties=prediction.normalized_uncertainties,
        support_score=0.0,
    ).use_surrogate

    mismatched = (
        samples[0],
        samples[1],
        TeacherSample(
            sequences=samples[2].sequences,
            outputs=samples[2].outputs,
            group_id=samples[2].group_id,
            output_target_bins=(2, 12),
        ),
    )
    with pytest.raises(ValueError, match="paper_target_bins metadata does not match"):
        train_linear_ensemble(
            mismatched,
            output_labels=labels,
            output_normalizations=normalizations,
            trace_paths=(trace_path,),
            ensemble_size=2,
        )


def test_trace_can_group_sibling_objectives_by_input_batch(tmp_path: Path) -> None:
    trace_path = tmp_path / "batch-grouped.jsonl"
    program = build_constant_program()

    with trace_program_constraints(
        program,
        JsonlTraceWriter(trace_path),
        run_id="run-0",
        group_id="evo2-seed-0",
        group_by_input_batch=True,
    ):
        program.run()

    rows = [TraceRow.model_validate_json(line) for line in trace_path.read_text().splitlines()]
    assert len({row.group_id for row in rows}) == 1
    assert rows[0].group_id.startswith("evo2-seed-0:batch-")
    assert len(rows[0].group_id.rsplit("-", 1)[1]) == 64


def test_trace_freezes_contract_before_runtime_seed_injection(tmp_path: Path) -> None:
    trace_path = tmp_path / "seeded.jsonl"
    seen_seeds: list[int | None] = []

    def seeded_objective(
        inputs: list[tuple[Any, ...]],
        config: dict[str, Any] | None,
    ) -> list[ConstraintOutput]:
        assert config is not None
        seen_seeds.append(config["seed"])
        return [ConstraintOutput(score=0.5) for _ in inputs]

    def build_seeded_program() -> Program:
        segment = Segment(sequence="ACGT", sequence_type="dna")
        optimizer = RejectionSamplingOptimizer(
            constructs=[Construct([segment])],
            generators=[],
            constraints=[
                Constraint(
                    inputs=[segment],
                    function=seeded_objective,
                    function_config={"seed": None, "fixed": "contract"},
                    label="seeded",
                )
            ],
            config=RejectionSamplingOptimizerConfig(
                num_samples=1,
                num_results=1,
                proposal_source="existing_results",
            ),
        )
        return Program(optimizers=[optimizer], num_results=1, seed=17)

    program = build_seeded_program()

    with trace_program_constraints(
        program,
        JsonlTraceWriter(trace_path),
        run_id="seeded-run",
        group_id="seeded-group",
    ):
        program.run()

    [row] = [
        TraceRow.model_validate_json(line) for line in trace_path.read_text().splitlines()
    ]
    assert len(seen_seeds) == 1
    assert isinstance(seen_seeds[0], int)
    assert row.schema_version == "1.1"
    assert row.constraint_config_scope == "pre_run_contract"
    assert row.program_seed == 17
    assert row.program_sha256 == program_signature(build_seeded_program()).sha256
    assert row.constraint_config == {"seed": None, "fixed": "contract"}
    validate_teacher_trace_contract(
        (trace_path,),
        program=build_seeded_program(),
        optimizer_index=0,
        constraint_labels=("seeded",),
    )

    drifted_path = tmp_path / "seeded-drifted.jsonl"
    drifted_path.write_text(
        row.model_copy(update={"constraint_config": {"seed": 3, "fixed": "contract"}})
        .model_dump_json()
        + "\n"
    )
    with pytest.raises(ValueError, match="teacher trace contract differs"):
        validate_teacher_trace_contract(
            (drifted_path,),
            program=build_seeded_program(),
            optimizer_index=0,
            constraint_labels=("seeded",),
        )


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
    assert payload["protocol"]["hardware_match_required"] is True
    hardware = dict(payload["hardware"])
    local_host = hardware.pop("local_host")
    assert hardware == {
        "device": "local",
        "accelerator": None,
        "context_id": "local-process",
        "pairing": "both arms run sequentially in the same process",
        "max_containers_per_service": None,
        "retries": None,
        "scaledown_window_seconds": None,
        "identity_level": "same_process",
        "same_physical_accelerator_verified": True,
    }
    assert local_host["hostname"]
    assert local_host["machine"]
    assert local_host["cpu_model"]
    assert local_host["hardware_threads"] >= 1
    assert local_host["memory_bytes"] > 0
    assert local_host["memory_scope"] == "os_visible"
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
            {
                "normalized_values": (0.25, 0.75),
                "normalized_uncertainties": (0.0, 0.0),
                "support_score": float("nan"),
            },
        ),
    )
    invalid_uncertainty = evaluator._gate(
        (),
        SurrogatePrediction(
            (),
            {
                "normalized_values": (0.25, 0.75),
                "normalized_uncertainties": (0.0, float("nan")),
                "support_score": 0.0,
            },
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


def test_sequence_bin_gate_uses_normalized_ensemble_spread() -> None:
    schema = SequenceFeatureSchema(
        sequence_type="dna",
        alphabet="AC",
        kmer_size=1,
        include_composition=False,
    )
    first = ((0.4, 0.4), *((0.0, 0.0),) * 6)
    second = ((0.6, 0.6), *((0.0, 0.0),) * 6)
    model = LinearEnsembleModel(
        input_schemas=(schema, schema, schema),
        output_labels=("enformer_pattern_l1_sum", "borzoi_pattern_l1_sum"),
        output_normalizations=evo2_output_normalizations(
            ("enformer_pattern_l1_sum", "borzoi_pattern_l1_sum")
        ),
        coefficients=(first, second),
        feature_center=(0.0,) * 6,
        feature_scale=(1.0,) * 6,
        support_threshold=10.0,
        uncertainty_threshold=0.11,
        calibration_absolute_error=(0.0, 0.0),
    )
    prediction = LinearEnsemblePredictor(model).predict(("C", "A" * 128, "C"))

    assert prediction.normalized_uncertainties == pytest.approx((0.1, 0.1))
    assert prediction.uncertainties == pytest.approx(
        (0.1, 0.4 * BORZOI_LCB_MAXIMUM_L1_PER_BIN)
    )
    assert linear_gate_decision(
        model,
        values=prediction.normalized_values,
        uncertainties=prediction.normalized_uncertainties,
        support_score=prediction.support_score,
    ).use_surrogate
    assert linear_gate_decision(
        model,
        values=(0.5, 0.5),
        uncertainties=(0.1, 0.12),
        support_score=0.0,
    ).reason == "uncertain"
    assert linear_gate_decision(
        model,
        values=(0.5, 1.01),
        uncertainties=(0.0, 0.0),
        support_score=0.0,
    ).reason == "prediction_out_of_range"


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
