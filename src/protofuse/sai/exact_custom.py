"""Exact process-parallel execution for released CUSTOM body-MFE scoring."""

from __future__ import annotations

import math
import multiprocessing
import os
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal, cast

from proto_language.core import ConstraintOutput, Sequence

from protofuse.phillip.custom_constraints import (
    CustomMetricConfig,
    _outputs,
)

MAX_CUSTOM_MFE_WORKERS = 8
FROZEN_CUSTOM_MFE_WINDOW_STRIDE = 8
FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL = -0.1349942934412618
FROZEN_CUSTOM_MFE_SLOPE = 0.9696276376691415
FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL = 0.30179657656023395

ConstraintInputs = list[tuple[Sequence, ...]]
ConstraintFunction = Callable[[ConstraintInputs, CustomMetricConfig], list[ConstraintOutput]]


@dataclass(frozen=True)
class CustomMFEChunk:
    """One ordered, picklable unit of released-CUSTOM work."""

    index: int
    sequences: tuple[str, ...]
    target_tissue: Literal["Lung"]


@dataclass(frozen=True)
class CustomMFEChunkResult:
    """Raw MFE values returned in the same order as a chunk's sequences."""

    index: int
    values: tuple[float, ...]
    uncertainties: tuple[float, ...] = ()


@dataclass(frozen=True)
class SampledMFEChunk:
    """One calibrated, fixed-stride approximation unit."""

    index: int
    sequences: tuple[str, ...]
    window_stride: int
    intercept: float
    slope: float


def released_custom_mfe_worker(chunk: CustomMFEChunk) -> CustomMFEChunkResult:
    """Call pinned released ``TissueOptimizer.MFE()`` for one ordered chunk."""

    from custom import TissueOptimizer  # type: ignore[import-untyped]

    optimizer = cast(
        Any,
        TissueOptimizer(
            chunk.target_tissue,
            n_pool=len(chunk.sequences),
            degree=0.5,
            prob_original=0.0,
        ),
    )
    optimizer.pool = list(chunk.sequences)
    values = tuple(float(value) for value in optimizer.MFE())
    if len(values) != len(chunk.sequences) or any(not math.isfinite(value) for value in values):
        raise ValueError("released CUSTOM returned invalid body-MFE values")
    return CustomMFEChunkResult(index=chunk.index, values=values)


def sampled_custom_mfe_worker(chunk: SampledMFEChunk) -> CustomMFEChunkResult:
    """Approximate CUSTOM body MFE from a frozen subset of its 40-nt windows."""

    import RNA  # type: ignore[import-untyped]

    values: list[float] = []
    uncertainties: list[float] = []
    for sequence in chunk.sequences:
        window_values = [
            float(RNA.fold(sequence[start : start + 40])[1])
            for start in range(40, len(sequence) - 39, chunk.window_stride)
        ]
        if not window_values:
            raise ValueError("sampled CUSTOM MFE requires at least one 40-nt body window")
        sampled_mean = sum(window_values) / len(window_values)
        corrected = chunk.intercept + chunk.slope * sampled_mean
        first_member = chunk.intercept + chunk.slope * (
            sum(window_values[::2]) / len(window_values[::2])
        )
        second_values = window_values[1::2]
        second_member = (
            chunk.intercept + chunk.slope * (sum(second_values) / len(second_values))
            if second_values
            else first_member
        )
        if not math.isfinite(corrected):
            raise ValueError("sampled CUSTOM MFE returned a non-finite value")
        values.append(corrected)
        uncertainties.append(abs(first_member - second_member) / 2.0)
    return CustomMFEChunkResult(
        index=chunk.index,
        values=tuple(values),
        uncertainties=tuple(uncertainties),
    )


class ExactCustomMfeEvaluator:
    """Evaluate body MFE in ordered worker chunks with exact serial fallback."""

    def __init__(
        self,
        parent_function: ConstraintFunction,
        parent_config: CustomMetricConfig,
        workers: int,
    ) -> None:
        if workers < 1:
            raise ValueError("workers must be positive")
        available_workers = os.cpu_count() or 1
        self.workers = min(workers, MAX_CUSTOM_MFE_WORKERS, available_workers)
        self.parent_function = parent_function
        self.parent_config = parent_config
        self.objectives = ("custom_mfe",)
        self.routing_counts = {"parallel": 0, "parent": 0}
        self.routing_reasons: Counter[str] = Counter()
        self.batch_counts = {"parallel": 0, "parent": 0, "parallel_failures": 0}
        self.timing_seconds = {"parallel": 0.0, "parent": 0.0}
        self.last_worker_count = 0
        self.last_parallel_error_type: str | None = None

    def evaluate(
        self,
        input_sequences: ConstraintInputs,
        config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        del config
        if not input_sequences:
            return []

        parallel_started = perf_counter()
        try:
            values = self._parallel_values(input_sequences, self.parent_config)
            outputs = _outputs(
                values,
                metric="mfe_kcal_mol",
                lower=-200.0,
                upper=0.0,
                maximize=False,
            )
        except Exception as error:  # noqa: BLE001 - exact parent fallback is mandatory
            self.timing_seconds["parallel"] += perf_counter() - parallel_started
            self.batch_counts["parallel_failures"] += 1
            self.last_parallel_error_type = type(error).__name__
            reason = f"parallel_error:{type(error).__name__}"
            self.routing_reasons[reason] += len(input_sequences)
            return self._fallback(input_sequences)

        self.timing_seconds["parallel"] += perf_counter() - parallel_started
        self.batch_counts["parallel"] += 1
        self.routing_counts["parallel"] += len(input_sequences)
        self.routing_reasons["exact_parallel"] += len(input_sequences)
        self.last_parallel_error_type = None
        return outputs

    def __call__(
        self,
        input_sequences: ConstraintInputs,
        config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        return self.evaluate(input_sequences, config)

    def _parallel_values(
        self,
        input_sequences: ConstraintInputs,
        config: CustomMetricConfig,
    ) -> list[float]:
        sequences = [sequence.sequence for (sequence,) in input_sequences]
        worker_count = min(self.workers, len(sequences))
        self.last_worker_count = worker_count
        chunks = _ordered_chunks(sequences, worker_count, config.target_tissue)
        with ProcessPoolExecutor(
            max_workers=worker_count,
            mp_context=multiprocessing.get_context("spawn"),
        ) as executor:
            chunk_results = list(executor.map(released_custom_mfe_worker, chunks))
        ordered_results = sorted(chunk_results, key=lambda result: result.index)
        values = [value for result in ordered_results for value in result.values]
        if len(values) != len(sequences):
            raise ValueError(
                f"parallel CUSTOM returned {len(values)} values for {len(sequences)} inputs"
            )
        return values

    def _fallback(
        self,
        input_sequences: ConstraintInputs,
    ) -> list[ConstraintOutput]:
        fallback_started = perf_counter()
        try:
            return list(self.parent_function(input_sequences, self.parent_config))
        finally:
            self.timing_seconds["parent"] += perf_counter() - fallback_started
            self.batch_counts["parent"] += 1
            self.routing_counts["parent"] += len(input_sequences)


class SampledCustomMfeEvaluator(ExactCustomMfeEvaluator):
    """Calibrated fixed-stride MFE approximation with exact parent fallback."""

    def __init__(
        self,
        parent_function: ConstraintFunction,
        parent_config: CustomMetricConfig,
        workers: int,
        *,
        window_stride: int,
        intercept: float,
        slope: float,
        uncertainty_threshold: float = (
            FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
        ),
    ) -> None:
        if window_stride < 2:
            raise ValueError("sampled window_stride must be at least 2")
        if not math.isfinite(intercept) or not math.isfinite(slope) or slope <= 0.0:
            raise ValueError("sampled MFE correction must be finite with positive slope")
        if uncertainty_threshold < 0.0 or math.isnan(uncertainty_threshold):
            raise ValueError("sampled MFE uncertainty threshold must be non-negative")
        super().__init__(parent_function, parent_config, workers)
        self.window_stride = window_stride
        self.intercept = intercept
        self.slope = slope
        self.uncertainty_threshold = uncertainty_threshold
        self.routing_counts = {"surrogate": 0, "full_model": 0}
        self.batch_counts = {"surrogate": 0, "full_model": 0, "parallel_failures": 0}
        self.timing_seconds = {"surrogate": 0.0, "gate": 0.0, "full_model": 0.0}

    def evaluate(
        self,
        input_sequences: ConstraintInputs,
        config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        del config
        if not input_sequences:
            return []
        started = perf_counter()
        try:
            values, uncertainties = self._parallel_predictions(
                input_sequences,
                self.parent_config,
            )
            outputs = _outputs(
                values,
                metric="mfe_kcal_mol",
                lower=-200.0,
                upper=0.0,
                maximize=False,
            )
        except Exception as error:  # noqa: BLE001 - exact parent fallback is mandatory
            self.timing_seconds["surrogate"] += perf_counter() - started
            self.batch_counts["parallel_failures"] += 1
            self.last_parallel_error_type = type(error).__name__
            reason = f"sampled_mfe_error:{type(error).__name__}"
            self.routing_reasons[reason] += len(input_sequences)
            return self._fallback_sampled(input_sequences, reason=reason)

        self.timing_seconds["surrogate"] += perf_counter() - started
        self.batch_counts["surrogate"] += 1
        self.last_parallel_error_type = None
        gate_started = perf_counter()
        try:
            rejection_reasons: dict[int, str] = {}
            for index, uncertainty in enumerate(uncertainties):
                if not math.isfinite(uncertainty) or uncertainty < 0.0:
                    rejection_reasons[index] = "sampled_mfe_invalid_uncertainty"
                elif uncertainty > self.uncertainty_threshold:
                    rejection_reasons[index] = "sampled_mfe_uncertain"
            rejected_indexes = sorted(rejection_reasons)
        finally:
            self.timing_seconds["gate"] += perf_counter() - gate_started
        fallback_by_index: dict[int, ConstraintOutput] = {}
        if rejected_indexes:
            fallback_inputs = [input_sequences[index] for index in rejected_indexes]
            fallback_outputs = self._parent_outputs(fallback_inputs)
            fallback_by_index = dict(
                zip(rejected_indexes, fallback_outputs, strict=True)
            )
            self.batch_counts["full_model"] += 1
            self.routing_counts["full_model"] += len(rejected_indexes)
            self.routing_reasons.update(rejection_reasons.values())

        accepted_count = len(input_sequences) - len(rejected_indexes)
        self.routing_counts["surrogate"] += accepted_count
        self.routing_reasons["frozen_sampled_window_mfe"] += accepted_count
        routed: list[ConstraintOutput] = []
        for index, (output, uncertainty) in enumerate(
            zip(outputs, uncertainties, strict=True)
        ):
            if index in fallback_by_index:
                reason = rejection_reasons[index]
                routed.append(
                    fallback_by_index[index].model_copy(
                        update={
                            "metadata": {
                                **fallback_by_index[index].metadata,
                                "protofuse_route": "full_model",
                                "protofuse_reason": reason,
                                "protofuse_sampled_uncertainty_kcal_mol": (
                                    uncertainty if math.isfinite(uncertainty) else None
                                ),
                            }
                        }
                    )
                )
            else:
                routed.append(
                    output.model_copy(
                        update={
                            "metadata": {
                                **output.metadata,
                                "protofuse_route": "surrogate",
                                "protofuse_reason": "frozen_sampled_window_mfe",
                                "protofuse_window_stride": self.window_stride,
                                "protofuse_sampled_uncertainty_kcal_mol": uncertainty,
                            }
                        }
                    )
                )
        return routed

    def _parallel_values(
        self,
        input_sequences: ConstraintInputs,
        config: CustomMetricConfig,
    ) -> list[float]:
        values, _ = self._parallel_predictions(input_sequences, config)
        return values

    def _parallel_predictions(
        self,
        input_sequences: ConstraintInputs,
        config: CustomMetricConfig,
    ) -> tuple[list[float], list[float]]:
        sequences = [sequence.sequence for (sequence,) in input_sequences]
        worker_count = min(self.workers, len(sequences))
        self.last_worker_count = worker_count
        chunk_size = math.ceil(len(sequences) / worker_count)
        chunks = [
            SampledMFEChunk(
                index=index,
                sequences=tuple(sequences[start : start + chunk_size]),
                window_stride=self.window_stride,
                intercept=self.intercept,
                slope=self.slope,
            )
            for index, start in enumerate(range(0, len(sequences), chunk_size))
        ]
        with ProcessPoolExecutor(
            max_workers=worker_count,
            mp_context=multiprocessing.get_context("spawn"),
        ) as executor:
            chunk_results = list(executor.map(sampled_custom_mfe_worker, chunks))
        values = [
            value
            for result in sorted(chunk_results, key=lambda item: item.index)
            for value in result.values
        ]
        uncertainties = [
            value
            for result in sorted(chunk_results, key=lambda item: item.index)
            for value in result.uncertainties
        ]
        if len(values) != len(sequences) or len(uncertainties) != len(sequences):
            raise ValueError(
                "sampled CUSTOM returned incomplete values or uncertainties"
            )
        return values, uncertainties

    def _fallback_sampled(
        self,
        input_sequences: ConstraintInputs,
        *,
        reason: str,
    ) -> list[ConstraintOutput]:
        outputs = self._parent_outputs(input_sequences)
        self.batch_counts["full_model"] += 1
        self.routing_counts["full_model"] += len(input_sequences)
        return [
            output.model_copy(
                update={
                    "metadata": {
                        **output.metadata,
                        "protofuse_route": "full_model",
                        "protofuse_reason": reason,
                    }
                }
            )
            for output in outputs
        ]

    def _parent_outputs(
        self,
        input_sequences: ConstraintInputs,
    ) -> list[ConstraintOutput]:
        fallback_started = perf_counter()
        try:
            outputs = list(self.parent_function(input_sequences, self.parent_config))
            if len(outputs) != len(input_sequences):
                raise ValueError(
                    f"CUSTOM MFE parent returned {len(outputs)} outputs for "
                    f"{len(input_sequences)} inputs"
                )
            return outputs
        finally:
            self.timing_seconds["full_model"] += perf_counter() - fallback_started


def _ordered_chunks(
    sequences: list[str],
    worker_count: int,
    target_tissue: Literal["Lung"],
) -> list[CustomMFEChunk]:
    chunk_size = math.ceil(len(sequences) / worker_count)
    return [
        CustomMFEChunk(
            index=index,
            sequences=tuple(sequences[start : start + chunk_size]),
            target_tissue=target_tissue,
        )
        for index, start in enumerate(range(0, len(sequences), chunk_size))
    ]
