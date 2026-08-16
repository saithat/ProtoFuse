from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, cast

import pytest
import RNA  # type: ignore[import-untyped]
from proto_language.core import ConstraintOutput, Sequence

from protofuse.phillip.custom_constraints import CustomMetricConfig, custom_mfe_constraint
from protofuse.sai.analyzer import load_reviewed_program
from protofuse.sai.exact_custom import (
    FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL,
    ExactCustomMfeEvaluator,
    SampledCustomMfeEvaluator,
    SampledMFEChunk,
    sampled_custom_mfe_worker,
)
from protofuse.sai.transform import build_exact_custom_mfe_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COLLECTION = REPO_ROOT / "proto_programs/generated/custom-egfp-lung"


def _inputs() -> list[tuple[Sequence, ...]]:
    sequences = (
        "ATGGCTGAACTG" * 8,
        "GCCATCGAGTTC" * 8,
        "GGTACCAAGCTT" * 8,
    )
    return [(Sequence(sequence=value, sequence_type="dna"),) for value in sequences]


def _float_bits(value: float) -> bytes:
    return struct.pack("!d", value)


def test_exact_custom_mfe_matches_serial_bits_order_and_metadata() -> None:
    inputs = _inputs()
    config = CustomMetricConfig()
    expected = custom_mfe_constraint(inputs, config)
    evaluator = ExactCustomMfeEvaluator(custom_mfe_constraint, config, workers=100)

    actual = evaluator.evaluate(inputs, config)

    assert len(actual) == len(expected)
    assert [_float_bits(output.score) for output in actual] == [
        _float_bits(output.score) for output in expected
    ]
    assert [output.metadata for output in actual] == [output.metadata for output in expected]
    assert [
        _float_bits(float(output.metadata["mfe_kcal_mol"])) for output in actual
    ] == [
        _float_bits(float(output.metadata["mfe_kcal_mol"])) for output in expected
    ]
    assert evaluator.last_worker_count == len(inputs)
    assert evaluator.workers <= 8
    assert evaluator.routing_counts == {"parallel": len(inputs), "parent": 0}
    assert evaluator.routing_reasons == {"exact_parallel": len(inputs)}
    assert evaluator.batch_counts == {"parallel": 1, "parent": 0, "parallel_failures": 0}
    assert evaluator.timing_seconds["parallel"] >= 0.0


def test_exact_custom_mfe_falls_back_to_original_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()[:2]
    config = CustomMetricConfig()
    fallback_calls: list[int] = []

    def original(
        values: list[tuple[Sequence, ...]],
        original_config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        fallback_calls.append(len(values))
        return cast(list[ConstraintOutput], custom_mfe_constraint(values, original_config))

    evaluator = ExactCustomMfeEvaluator(original, config, workers=2)
    expected = original(inputs, config)
    fallback_calls.clear()

    def fail_parallel(
        values: list[tuple[Sequence, ...]],
        original_config: CustomMetricConfig,
    ) -> list[float]:
        del values, original_config
        raise RuntimeError("injected worker failure")

    monkeypatch.setattr(evaluator, "_parallel_values", fail_parallel)
    actual = evaluator.evaluate(inputs, config)

    assert actual == expected
    assert fallback_calls == [len(inputs)]
    assert evaluator.last_parallel_error_type == "RuntimeError"
    assert evaluator.routing_counts == {"parallel": 0, "parent": len(inputs)}
    assert evaluator.routing_reasons == {"parallel_error:RuntimeError": len(inputs)}
    assert evaluator.batch_counts == {"parallel": 0, "parent": 1, "parallel_failures": 1}
    assert evaluator.timing_seconds["parent"] >= 0.0


def test_exact_custom_bundle_does_not_rescore_and_reorder_exact_results() -> None:
    reference = load_reviewed_program(CUSTOM_COLLECTION, program_id="design-001")
    fused = build_exact_custom_mfe_bundle(reference.program, workers=8).apply(
        reference.program
    )

    assert len(fused.optimizers) == len(reference.program.optimizers)
    assert cast(Any, fused)._protofuse_validation_work[0] == {}


def test_sampled_custom_mfe_worker_preserves_order_and_prediction_formula() -> None:
    sequences = tuple(value[0].sequence for value in _inputs()[:2])
    chunk = SampledMFEChunk(
        index=7,
        sequences=sequences,
        window_stride=4,
        intercept=-0.125,
        slope=0.95,
    )

    result = sampled_custom_mfe_worker(chunk)

    expected_values: list[float] = []
    expected_uncertainties: list[float] = []
    for sequence in sequences:
        window_values = [
            float(RNA.fold(sequence[start : start + 40])[1])
            for start in range(40, len(sequence) - 39, chunk.window_stride)
        ]
        expected_values.append(
            chunk.intercept + chunk.slope * (sum(window_values) / len(window_values))
        )
        first_member = chunk.intercept + chunk.slope * (
            sum(window_values[::2]) / len(window_values[::2])
        )
        second_member = chunk.intercept + chunk.slope * (
            sum(window_values[1::2]) / len(window_values[1::2])
        )
        expected_uncertainties.append(abs(first_member - second_member) / 2.0)

    assert result.index == chunk.index
    assert [_float_bits(value) for value in result.values] == [
        _float_bits(value) for value in expected_values
    ]
    assert [_float_bits(value) for value in result.uncertainties] == [
        _float_bits(value) for value in expected_uncertainties
    ]


def test_sampled_custom_mfe_routes_each_item_without_reordering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()
    config = CustomMetricConfig()
    parent_calls: list[list[str]] = []

    def parent(
        values: list[tuple[Sequence, ...]],
        parent_config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        del parent_config
        parent_calls.append([value[0].sequence for value in values])
        return [
            ConstraintOutput(
                score=0.2 + 0.1 * index,
                metadata={"parent_sequence": value[0].sequence},
            )
            for index, value in enumerate(values)
        ]

    evaluator = SampledCustomMfeEvaluator(
        parent,
        config,
        workers=2,
        window_stride=8,
        intercept=-0.1,
        slope=0.9,
        uncertainty_threshold=0.25,
    )

    def predictions(
        values: list[tuple[Sequence, ...]],
        prediction_config: CustomMetricConfig,
    ) -> tuple[list[float], list[float]]:
        del values, prediction_config
        return [-10.0, -20.0, -30.0], [0.1, 0.5, float("nan")]

    monkeypatch.setattr(evaluator, "_parallel_predictions", predictions)
    actual = evaluator.evaluate(inputs, config)

    assert parent_calls == [[inputs[1][0].sequence, inputs[2][0].sequence]]
    assert actual[0].metadata == {
        "mfe_kcal_mol": -10.0,
        "protofuse_route": "surrogate",
        "protofuse_reason": "frozen_sampled_window_mfe",
        "protofuse_window_stride": 8,
        "protofuse_sampled_uncertainty_kcal_mol": 0.1,
    }
    assert actual[1].metadata == {
        "parent_sequence": inputs[1][0].sequence,
        "protofuse_route": "full_model",
        "protofuse_reason": "sampled_mfe_uncertain",
        "protofuse_sampled_uncertainty_kcal_mol": 0.5,
    }
    assert actual[2].metadata == {
        "parent_sequence": inputs[2][0].sequence,
        "protofuse_route": "full_model",
        "protofuse_reason": "sampled_mfe_invalid_uncertainty",
        "protofuse_sampled_uncertainty_kcal_mol": None,
    }
    assert [output.score for output in actual] == pytest.approx([0.95, 0.2, 0.3])
    json.dumps([output.metadata for output in actual], allow_nan=False)
    assert evaluator.routing_counts == {"surrogate": 1, "full_model": 2}
    assert evaluator.routing_reasons == {
        "frozen_sampled_window_mfe": 1,
        "sampled_mfe_uncertain": 1,
        "sampled_mfe_invalid_uncertainty": 1,
    }
    assert evaluator.batch_counts == {
        "surrogate": 1,
        "full_model": 1,
        "parallel_failures": 0,
    }
    assert evaluator.timing_seconds["gate"] >= 0.0
    assert evaluator.timing_seconds["full_model"] >= 0.0


def test_sampled_custom_mfe_fails_closed_on_surrogate_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()[:2]
    config = CustomMetricConfig()
    parent_calls: list[list[str]] = []

    def parent(
        values: list[tuple[Sequence, ...]],
        parent_config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        del parent_config
        parent_calls.append([value[0].sequence for value in values])
        return [
            ConstraintOutput(score=0.4, metadata={"parent_sequence": value[0].sequence})
            for value in values
        ]

    evaluator = SampledCustomMfeEvaluator(
        parent,
        config,
        workers=2,
        window_stride=8,
        intercept=-0.1,
        slope=0.9,
    )
    assert (
        evaluator.uncertainty_threshold
        == FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
    )

    def fail_predictions(
        values: list[tuple[Sequence, ...]],
        prediction_config: CustomMetricConfig,
    ) -> tuple[list[float], list[float]]:
        del values, prediction_config
        raise RuntimeError("injected sampled worker failure")

    monkeypatch.setattr(evaluator, "_parallel_predictions", fail_predictions)
    actual = evaluator.evaluate(inputs, config)

    assert parent_calls == [[value[0].sequence for value in inputs]]
    assert [output.metadata["parent_sequence"] for output in actual] == [
        value[0].sequence for value in inputs
    ]
    assert {output.metadata["protofuse_route"] for output in actual} == {"full_model"}
    assert {output.metadata["protofuse_reason"] for output in actual} == {
        "sampled_mfe_error:RuntimeError"
    }
    assert evaluator.last_parallel_error_type == "RuntimeError"
    assert evaluator.routing_counts == {"surrogate": 0, "full_model": len(inputs)}
    assert evaluator.routing_reasons == {
        "sampled_mfe_error:RuntimeError": len(inputs)
    }
    assert evaluator.batch_counts == {
        "surrogate": 0,
        "full_model": 1,
        "parallel_failures": 1,
    }


def test_sampled_custom_mfe_rejects_incomplete_parent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()[:1]
    config = CustomMetricConfig()

    def incomplete_parent(
        values: list[tuple[Sequence, ...]],
        parent_config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        del values, parent_config
        return []

    evaluator = SampledCustomMfeEvaluator(
        incomplete_parent,
        config,
        workers=1,
        window_stride=8,
        intercept=-0.1,
        slope=0.9,
        uncertainty_threshold=0.25,
    )

    def uncertain_prediction(
        values: list[tuple[Sequence, ...]],
        prediction_config: CustomMetricConfig,
    ) -> tuple[list[float], list[float]]:
        del values, prediction_config
        return [-10.0], [0.5]

    monkeypatch.setattr(evaluator, "_parallel_predictions", uncertain_prediction)

    with pytest.raises(ValueError, match="parent returned 0 outputs for 1 inputs"):
        evaluator.evaluate(inputs, config)
