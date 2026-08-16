from pathlib import Path
from typing import Any, cast

import pytest
from proto_language.core import Constraint, ConstraintOutput, Construct, Program, Segment
from proto_language.optimizer import (
    RejectionSamplingOptimizer,
    RejectionSamplingOptimizerConfig,
)

from protofuse.sai.artifacts import FusionManifest, write_unreviewed_fusion_artifact
from protofuse.sai.model import LinearEnsembleModel, SequenceFeatureSchema
from protofuse.sai.signatures import step_group_signature
from protofuse.sai.transform import transform_with_artifact


def low_score(
    inputs: list[tuple[Any, ...]],
    config: dict[str, Any] | None,
) -> list[ConstraintOutput]:
    del config
    return [ConstraintOutput(score=0.25) for _ in inputs]


def build_filter_program() -> Program:
    segment = Segment(sequence="ACGT", sequence_type="dna", label="target")
    optimizer = RejectionSamplingOptimizer(
        constructs=[Construct([segment])],
        generators=[],
        constraints=[
            Constraint(
                inputs=[segment],
                function=low_score,
                label="low",
                threshold=0.5,
            )
        ],
        config=RejectionSamplingOptimizerConfig(
            num_samples=1,
            num_results=1,
            proposal_source="existing_results",
        ),
    )
    return Program(optimizers=[optimizer], num_results=1, seed=17)


def write_filter_artifact(root: Path) -> Any:
    program = build_filter_program()
    signature = step_group_signature(
        program,
        optimizer_index=0,
        constraint_labels=("low",),
    )
    schema = SequenceFeatureSchema(
        sequence_type="dna",
        alphabet="ACGT",
        kmer_size=1,
        include_composition=False,
        expected_length=4,
    )
    matrix = ((0.25,), (0.0,), (0.0,), (0.0,), (0.0,))
    model = LinearEnsembleModel(
        input_schemas=(schema,),
        output_labels=("low",),
        coefficients=(matrix, matrix),
        feature_center=(0.0, 0.0, 0.0, 0.0),
        feature_scale=(1.0, 1.0, 1.0, 1.0),
        support_threshold=10.0,
        uncertainty_threshold=0.0,
        calibration_absolute_error=(0.0,),
    )
    manifest = FusionManifest(
        fusion_id="filter-objective",
        version="1",
        optimizer_index=0,
        constraint_labels=("low",),
        group_signature=signature,
        group_signature_sha256=signature.sha256,
        model_sha256="0" * 64,
    )
    return write_unreviewed_fusion_artifact(root, manifest=manifest, model=model)


def test_transform_preserves_filter_threshold_and_final_parent_validation(
    tmp_path: Path,
) -> None:
    fused = transform_with_artifact(
        build_filter_program(),
        write_filter_artifact(tmp_path / "filter"),
    )

    routed = fused.optimizers[0].constraints[0]
    final = fused.optimizers[1].constraints[0]
    assert routed.threshold == pytest.approx(0.5)
    assert final.threshold == pytest.approx(0.5)

    fused.run()

    evaluator = cast(Any, fused)._protofuse_evaluators[0]
    validation = cast(Any, fused)._protofuse_validation_work[0]
    assert evaluator.routing_counts == {"surrogate": 1, "full_model": 0}
    assert validation["parent_item_evaluations"] == 1
    assert fused.constructs[0].joined_sequences[0].sequence == "ACGT"
