from __future__ import annotations

from pathlib import Path

import pytest

from protofuse.sai.model import (
    LinearEnsemblePredictor,
    SequenceFeatureSchema,
    featurize_inputs,
    sequence_fixed_context_sha256,
)
from protofuse.sai.router import BatchSelectiveRouter, GateDecision, SurrogatePrediction
from protofuse.sai.training import TeacherSample, prepare_training_data, train_ridge_ensemble


def test_selected_position_schema_preserves_legacy_defaults() -> None:
    legacy = SequenceFeatureSchema.model_validate(
        {
            "sequence_type": "protein",
            "alphabet": "ACDE",
            "kmer_size": 1,
            "stride": 1,
            "include_composition": False,
            "expected_length": 4,
            "position_encoding": "one_hot",
        }
    )
    assert legacy.include_kmers is True
    assert legacy.position_indices is None
    assert legacy.feature_count == 20

    selected = legacy.model_copy(
        update={
            "include_kmers": False,
            "position_indices": (1, 3),
        }
    )
    assert selected.feature_count == 8
    baseline = featurize_inputs(("AAAA",), (selected,))
    outside = featurize_inputs(("CAAA",), (selected,))
    inside = featurize_inputs(("ACAA",), (selected,))
    assert baseline == outside
    assert sum(left != right for left, right in zip(baseline, inside, strict=True)) == 2


@pytest.mark.parametrize(
    "updates,match",
    [
        (
            {
                "include_kmers": False,
                "include_composition": False,
                "position_encoding": "none",
                "position_indices": None,
            },
            "at least one feature family",
        ),
        ({"position_indices": ()}, "cannot be empty"),
        ({"position_indices": (2, 1)}, "strictly increasing"),
        ({"position_indices": (1, 1)}, "strictly increasing"),
        ({"position_indices": (1, 4)}, "outside"),
        (
            {
                "position_encoding": "none",
                "position_indices": None,
                "fixed_context_sha256": "a" * 64,
            },
            "fixed context requires",
        ),
    ],
)
def test_selected_position_schema_rejects_invalid_contracts(
    updates: dict[str, object],
    match: str,
) -> None:
    values: dict[str, object] = {
        "sequence_type": "protein",
        "alphabet": "ACDE",
        "include_kmers": False,
        "include_composition": False,
        "expected_length": 4,
        "position_encoding": "one_hot",
        "position_indices": (1, 3),
    }
    values.update(updates)
    with pytest.raises(ValueError, match=match):
        SequenceFeatureSchema.model_validate(values)


def test_grouped_ridge_round_trip_and_unseen_category_fallback(tmp_path: Path) -> None:
    alphabet = "ACDEF"
    schema = SequenceFeatureSchema(
        sequence_type="protein",
        alphabet=alphabet,
        include_kmers=False,
        include_composition=False,
        expected_length=4,
        position_encoding="one_hot",
        position_indices=(0, 2),
        fixed_context_sha256=sequence_fixed_context_sha256("AAAA", (0, 2)),
    )
    observed = "ACDE"
    samples = []
    for index in range(16):
        first = observed[index % len(observed)]
        second = observed[(index // len(observed)) % len(observed)]
        sequence = f"{first}A{second}A"
        first_value = observed.index(first) / 3.0
        second_value = observed.index(second) / 3.0
        samples.append(
            TeacherSample(
                sequences=(sequence,),
                outputs=(
                    0.1 + 0.4 * first_value + 0.2 * second_value,
                    0.2 + 0.1 * first_value + 0.3 * second_value,
                ),
                group_id=f"group-{index}",
            )
        )
    trace = tmp_path / "trace.jsonl"
    trace.write_text("ridge provenance\n")
    result = train_ridge_ensemble(
        tuple(samples),
        output_labels=("first", "second"),
        trace_paths=(trace,),
        schemas=(schema,),
        seed=7,
        ensemble_size=3,
        alpha_grid=(0.01, 0.1, 1.0),
    )
    model = result.model.model_validate_json(result.model.model_dump_json())
    predictor = LinearEnsemblePredictor(model)

    assert model.fit_method == "ridge"
    assert model.schema_version == "1.4"
    assert len(model.coefficients) == 3
    assert len(model.coefficients[0]) == schema.feature_count + 1
    assert len(model.ridge_alpha) == 2
    assert len(result.split.input_sha256) > 0
    assert result.metrics["ridge_bootstrap_recentered"] is True

    seen = predictor.predict(("AAA A".replace(" ", ""),))
    unseen = predictor.predict(("FAA A".replace(" ", ""),))
    assert seen.support_score <= model.support_threshold
    assert unseen.support_score > model.support_threshold
    with pytest.raises(ValueError, match="does not match expected"):
        predictor.predict(("AAA",))
    with pytest.raises(ValueError, match="fixed context differs"):
        predictor.predict(("AAAC",))
    router = BatchSelectiveRouter[str, str](
        surrogate=lambda items: [
            SurrogatePrediction(str(predictor.predict((item,)).values), {}) for item in items
        ],
        gate=lambda _item, _prediction: GateDecision(True, "calibrated_in_domain"),
        full_model=lambda items: ["parent" for _item in items],
    )
    [routed] = router(["AAAC"])
    assert routed.route == "full_model"
    assert routed.value == "parent"
    assert routed.reason == "surrogate_error:ValueError"


def test_grouped_split_rejects_identical_inputs_across_groups(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text("duplicate-input provenance\n")
    samples = (
        TeacherSample(sequences=("AAAA",), outputs=(0.1,), group_id="first"),
        TeacherSample(sequences=("AAAA",), outputs=(0.1,), group_id="second"),
        TeacherSample(sequences=("CAAA",), outputs=(0.2,), group_id="third"),
    )
    with pytest.raises(ValueError, match="identical teacher inputs span multiple group IDs"):
        prepare_training_data(
            samples,
            output_labels=("score",),
            trace_paths=(trace,),
            seed=1,
        )
