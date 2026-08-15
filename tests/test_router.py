from protofuse.sai import GateDecision, SelectiveRouter, SurrogatePrediction


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
