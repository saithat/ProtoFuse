"""Per-input surrogate routing with deterministic, fail-closed full-model fallback."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SurrogatePrediction[OutputT]:
    value: OutputT
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class GateDecision:
    use_surrogate: bool
    reason: str


@dataclass(frozen=True)
class RoutedResult[OutputT]:
    value: OutputT
    route: Literal["surrogate", "full_model"]
    reason: str


class SelectiveRouter[InputT, OutputT]:
    def __init__(
        self,
        *,
        surrogate: Callable[[InputT], SurrogatePrediction[OutputT]],
        gate: Callable[[InputT, SurrogatePrediction[OutputT]], GateDecision],
        full_model: Callable[[InputT], OutputT],
    ) -> None:
        self._surrogate = surrogate
        self._gate = gate
        self._full_model = full_model

    def __call__(self, item: InputT) -> RoutedResult[OutputT]:
        try:
            prediction = self._surrogate(item)
        except Exception as error:
            return self._fallback(item, f"surrogate_error:{type(error).__name__}")
        try:
            decision = self._gate(item, prediction)
        except Exception as error:
            return self._fallback(item, f"gate_error:{type(error).__name__}")
        if not decision.use_surrogate:
            return self._fallback(item, decision.reason)
        return RoutedResult(prediction.value, "surrogate", decision.reason)

    def _fallback(self, item: InputT, reason: str) -> RoutedResult[OutputT]:
        return RoutedResult(self._full_model(item), "full_model", reason)
