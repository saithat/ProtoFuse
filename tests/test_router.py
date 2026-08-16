import pytest

from protofuse.sai import (
    BatchSelectiveRouter,
    GateDecision,
    SelectiveRouter,
    SurrogatePrediction,
)
from protofuse.sai.router import BatchRoutingError


def test_router_uses_surrogate_only_when_gate_accepts() -> None:
    router = SelectiveRouter[int, int](
        surrogate=lambda value: SurrogatePrediction(value * 2, {"uncertainty": 0.01}),
        gate=lambda _value, prediction: GateDecision(
            prediction.metadata["uncertainty"] == 0.01,
            "calibrated_in_domain",
        ),
        full_model=lambda value: value * 10,
    )

    result = router(3)

    assert result.value == 6
    assert result.route == "surrogate"


def test_router_defers_and_fails_closed() -> None:
    deferred = SelectiveRouter[int, int](
        surrogate=lambda value: SurrogatePrediction(value * 2, {"uncertainty": 1.0}),
        gate=lambda _value, _prediction: GateDecision(False, "out_of_domain"),
        full_model=lambda value: value * 10,
    )
    failed = SelectiveRouter[int, int](
        surrogate=lambda _value: (_ for _ in ()).throw(RuntimeError("unavailable")),
        gate=lambda _value, _prediction: GateDecision(True, "unused"),
        full_model=lambda value: value * 10,
    )

    deferred_result = deferred(3)
    failed_result = failed(3)

    assert (deferred_result.value, deferred_result.route, deferred_result.reason) == (
        30,
        "full_model",
        "out_of_domain",
    )
    assert failed_result.value == 30
    assert failed_result.route == "full_model"
    assert failed_result.reason == "surrogate_error:RuntimeError"


def test_batch_router_preserves_order_and_falls_back_only_rejected_items() -> None:
    parent_batches: list[list[int]] = []
    router = BatchSelectiveRouter[int, int](
        surrogate=lambda values: [
            SurrogatePrediction(value * 2, {"accepted": value % 2 == 0})
            for value in values
        ],
        gate=lambda _value, prediction: GateDecision(
            bool(prediction.metadata["accepted"]),
            "accepted" if prediction.metadata["accepted"] else "uncertain",
        ),
        full_model=lambda values: parent_batches.append(list(values))
        or [value * 10 for value in values],
    )

    results = router([1, 2, 3, 4])

    assert [result.value for result in results] == [10, 4, 30, 8]
    assert [result.route for result in results] == [
        "full_model",
        "surrogate",
        "full_model",
        "surrogate",
    ]
    assert parent_batches == [[1, 3]]


def test_batch_router_fails_closed_on_surrogate_error_and_checks_parent_count() -> None:
    fallback = BatchSelectiveRouter[int, int](
        surrogate=lambda _values: (_ for _ in ()).throw(RuntimeError("offline")),
        gate=lambda _value, _prediction: GateDecision(True, "unused"),
        full_model=lambda values: [value * 10 for value in values],
    )
    invalid_parent = BatchSelectiveRouter[int, int](
        surrogate=lambda values: [SurrogatePrediction(value, {}) for value in values],
        gate=lambda _value, _prediction: GateDecision(False, "defer"),
        full_model=lambda _values: [],
    )

    results = fallback([1, 2])

    assert [result.value for result in results] == [10, 20]
    assert all(result.reason == "surrogate_error:RuntimeError" for result in results)
    with pytest.raises(BatchRoutingError, match="full model returned 0 results"):
        invalid_parent([1])
