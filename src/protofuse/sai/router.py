"""Per-input surrogate routing with deterministic, fail-closed full-model fallback."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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


class BatchRoutingError(RuntimeError):
    """Raised when a batch implementation violates its result-count contract."""


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


class BatchSelectiveRouter[InputT, OutputT]:
    """Route a batch per item while batching both surrogate and parent calls."""

    def __init__(
        self,
        *,
        surrogate: Callable[[Sequence[InputT]], Sequence[SurrogatePrediction[OutputT]]],
        gate: Callable[[InputT, SurrogatePrediction[OutputT]], GateDecision],
        full_model: Callable[[Sequence[InputT]], Sequence[OutputT]],
    ) -> None:
        self._surrogate = surrogate
        self._gate = gate
        self._full_model = full_model

    def __call__(self, items: Sequence[InputT]) -> list[RoutedResult[OutputT]]:
        if not items:
            return []
        try:
            predictions = list(self._surrogate(items))
            if len(predictions) != len(items):
                raise BatchRoutingError(
                    f"surrogate returned {len(predictions)} results for {len(items)} inputs"
                )
        except Exception as error:
            return self._fallback_all(items, f"surrogate_error:{type(error).__name__}")

        routed: list[RoutedResult[OutputT] | None] = [None] * len(items)
        fallback_indices: list[int] = []
        fallback_reasons: dict[int, str] = {}
        for index, (item, prediction) in enumerate(zip(items, predictions, strict=True)):
            try:
                decision = self._gate(item, prediction)
            except Exception as error:
                fallback_indices.append(index)
                fallback_reasons[index] = f"gate_error:{type(error).__name__}"
                continue
            if decision.use_surrogate:
                routed[index] = RoutedResult(
                    prediction.value,
                    "surrogate",
                    decision.reason,
                )
            else:
                fallback_indices.append(index)
                fallback_reasons[index] = decision.reason

        if fallback_indices:
            fallback_items = [items[index] for index in fallback_indices]
            parent_outputs = list(self._full_model(fallback_items))
            if len(parent_outputs) != len(fallback_items):
                raise BatchRoutingError(
                    f"full model returned {len(parent_outputs)} results for "
                    f"{len(fallback_items)} inputs"
                )
            for index, output in zip(fallback_indices, parent_outputs, strict=True):
                routed[index] = RoutedResult(
                    output,
                    "full_model",
                    fallback_reasons[index],
                )

        if any(result is None for result in routed):
            raise BatchRoutingError("router left one or more batch positions unresolved")
        return [result for result in routed if result is not None]

    def _fallback_all(
        self,
        items: Sequence[InputT],
        reason: str,
    ) -> list[RoutedResult[OutputT]]:
        outputs = list(self._full_model(items))
        if len(outputs) != len(items):
            raise BatchRoutingError(
                f"full model returned {len(outputs)} results for {len(items)} inputs"
            )
        return [RoutedResult(output, "full_model", reason) for output in outputs]
