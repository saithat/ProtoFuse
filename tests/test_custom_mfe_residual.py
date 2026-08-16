from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from proto_language.core import ConstraintOutput, Sequence

from protofuse.sai.custom_mfe_residual import (
    EXPECTED_WINDOWS,
    FittedResidualCandidate,
    ResidualCustomMfeEvaluator,
    ResidualDataset,
    ResidualGates,
    custom_mfe_residual_features,
    dataset_fingerprint,
    evaluate_residual_candidate,
    load_residual_dataset,
    residual_feature_names,
    save_residual_dataset,
)


class _IdentityScaler:
    def transform(self, values: np.ndarray) -> np.ndarray:
        return values


class _FixedMember:
    def __init__(self, predictions: np.ndarray) -> None:
        self.predictions = predictions

    def predict(self, values: np.ndarray) -> np.ndarray:
        return self.predictions[: len(values)]


def _dataset() -> ResidualDataset:
    actual = np.asarray([-4.0, -3.0, -2.0, -1.0])
    baseline = np.asarray([-3.8, -2.8, -1.8, -0.8])
    return ResidualDataset(
        groups=np.asarray(["audit"] * 4),
        input_hashes=np.asarray(["a", "b", "c", "d"]),
        actual=actual,
        baseline=baseline,
        baseline_uncertainty=np.asarray([0.1, 0.1, 0.1, 0.5]),
        features=np.zeros((4, 2)),
        trace_sha256=("1" * 64,),
    )


def test_position_sensitive_features_include_every_sampled_window() -> None:
    sequence = "ATGGCT" * 119 + "ATG"

    features, baseline, uncertainty = custom_mfe_residual_features(sequence)

    assert len(sequence) == 717
    assert len(features) == len(residual_feature_names())
    assert len([name for name in residual_feature_names() if name.startswith("window_mfe_")]) == (
        EXPECTED_WINDOWS
    )
    assert np.isfinite(features).all()
    assert np.isfinite(baseline)
    assert uncertainty >= 0.0


def test_dataset_cache_rejects_different_trace_content(tmp_path: Path) -> None:
    dataset = _dataset()
    cache = tmp_path / "features.npz"
    save_residual_dataset(cache, dataset)

    loaded = load_residual_dataset(cache, expected_trace_sha256=dataset.trace_sha256)
    assert np.array_equal(loaded.actual, dataset.actual)
    assert dataset_fingerprint(loaded.trace_sha256) == dataset_fingerprint(
        dataset.trace_sha256
    )

    with pytest.raises(ValueError, match="does not match"):
        load_residual_dataset(cache, expected_trace_sha256=("2" * 64,))


def test_residual_gate_compares_value_add_on_the_same_accepted_rows() -> None:
    dataset = _dataset()
    residual = np.asarray([-0.2, -0.2, -0.2, -0.2])
    candidate = FittedResidualCandidate(
        family="ridge",
        config={},
        scaler=_IdentityScaler(),  # type: ignore[arg-type]
        model=[_FixedMember(residual), _FixedMember(residual)],
        support_center=np.zeros(2),
        support_scale=np.ones(2),
        support_threshold=1.0,
        uncertainty_threshold=0.01,
        model_sha256="f" * 64,
    )

    report = evaluate_residual_candidate(
        candidate,
        dataset,
        groups=("audit",),
        gates=ResidualGates(min_relative_mae_improvement=0.90),
    )

    assert report["samples"]["accepted"] == 3
    assert report["samples"]["routing"]["baseline_uncertain"] == 1
    assert report["metrics"]["residual_mae_kcal_mol"] == pytest.approx(0.0)
    assert report["metrics"]["baseline_mae_kcal_mol_same_rows"] == pytest.approx(0.2)
    assert report["checks"]["relative_mae_improvement"] is True
    assert report["passed"] is True


def test_runtime_residual_routes_each_rejection_to_the_exact_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = [
        (Sequence(sequence="ATGGCT" * 16, sequence_type="dna"),),
        (Sequence(sequence="GCCATG" * 16, sequence_type="dna"),),
        (Sequence(sequence="GGTACC" * 16, sequence_type="dna"),),
    ]
    parent_calls: list[list[str]] = []

    def parent(
        values: list[tuple[Sequence, ...]],
        config: object,
    ) -> list[ConstraintOutput]:
        del config
        parent_calls.append([item[0].sequence for item in values])
        return [
            ConstraintOutput(score=0.5, metadata={"exact": item[0].sequence})
            for item in values
        ]

    candidate = FittedResidualCandidate(
        family="ridge",
        config={},
        scaler=_IdentityScaler(),  # type: ignore[arg-type]
        model=[_FixedMember(np.zeros(3)), _FixedMember(np.zeros(3))],
        support_center=np.zeros(2),
        support_scale=np.ones(2),
        support_threshold=1.0,
        uncertainty_threshold=0.05,
        model_sha256="f" * 64,
    )
    evaluator = ResidualCustomMfeEvaluator(
        parent,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        workers=1,
        candidate=candidate,
    )

    monkeypatch.setattr(
        evaluator,
        "_parallel_predictions",
        lambda values: (
            [-2.0, -2.0, -2.0],
            [0.1, 0.5, 0.1],
            [0.01, 0.01, 0.1],
            [0.5, 0.5, 0.5],
        ),
    )

    outputs = evaluator.evaluate(inputs, object())  # type: ignore[arg-type]

    assert parent_calls == [[inputs[1][0].sequence, inputs[2][0].sequence]]
    assert outputs[0].metadata["protofuse_route"] == "surrogate"
    assert outputs[1].metadata["protofuse_reason"] == "residual_mfe_baseline_uncertain"
    assert outputs[2].metadata["protofuse_reason"] == "residual_mfe_model_uncertain"
    assert outputs[1].metadata["exact"] == inputs[1][0].sequence
    assert outputs[2].metadata["exact"] == inputs[2][0].sequence
    assert evaluator.routing_counts == {"surrogate": 1, "full_model": 2}
