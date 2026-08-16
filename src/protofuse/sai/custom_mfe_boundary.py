"""Adaptive exact-boundary fusion for the CUSTOM full-pool task."""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast

import numpy as np
from proto_language.core import Constraint, ConstraintOutput, Program

from protofuse.phillip.custom_constraints import (
    CUSTOM_METRIC_LABELS,
    CustomPaperPoolOptimizer,
    ordered_pool_sha256,
    paper_composite_energies,
)
from protofuse.sai.custom_mfe_residual import (
    EXPECTED_WINDOWS,
    FittedResidualCandidate,
    ResidualDataset,
    _support_scores,
)
from protofuse.sai.exact_custom import (
    FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
    FROZEN_CUSTOM_MFE_SLOPE,
    FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL,
    FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
    SampledCustomMfeEvaluator,
)
from protofuse.sai.registry import FusionBundle
from protofuse.sai.signatures import step_group_signature
from protofuse.sai.training import _read_trace
from protofuse.sai.transform import (
    FusionCompatibilityError,
    _CustomMfeParallelConstraint,
    _reject_output_dependencies,
)

BOUNDARY_BUDGETS = (10, 20, 30, 50, 75, 100, 150, 200)
FULL_WINDOWS_PER_SEQUENCE = 638
TOP_K = 10


class AdaptiveBoundarySampledMfeEvaluator(SampledCustomMfeEvaluator):
    """Sample first, then exact-rescore a task-level ranking boundary."""

    def __init__(
        self,
        parent_function: Any,
        parent_config: Any,
        workers: int,
        *,
        boundary_budget: int,
        top_k: int,
        exact_mfe_extrema: bool,
        mfe_tail_budget: int = 0,
        window_stride: int = FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
        intercept: float = FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
        slope: float = FROZEN_CUSTOM_MFE_SLOPE,
        uncertainty_threshold: float = (
            FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
        ),
    ) -> None:
        if top_k < 1:
            raise ValueError("CUSTOM adaptive top_k must be positive")
        if boundary_budget < top_k:
            raise ValueError("CUSTOM boundary budget must be at least top_k")
        if mfe_tail_budget < 0:
            raise ValueError("CUSTOM MFE tail budget must be non-negative")
        super().__init__(
            parent_function,
            parent_config,
            workers,
            window_stride=window_stride,
            intercept=intercept,
            slope=slope,
            uncertainty_threshold=uncertainty_threshold,
        )
        self.boundary_budget = boundary_budget
        self.top_k = top_k
        self.mfe_tail_budget = max(mfe_tail_budget, int(exact_mfe_extrema))
        self._pending_exact_mask: tuple[bool, ...] = ()
        self.last_initial_ranking: tuple[int, ...] = ()
        self.boundary_reports: list[dict[str, Any]] = []

    def evaluate(
        self,
        input_sequences: list[tuple[Any, ...]],
        config: Any,
    ) -> list[ConstraintOutput]:
        outputs = super().evaluate(input_sequences, config)
        self._pending_exact_mask = tuple(
            output.metadata.get("protofuse_route") == "full_model"
            for output in outputs
        )
        return outputs

    def refine_optimizer(
        self,
        optimizer: AdaptiveCustomPaperPoolOptimizer,
        constraint: _CustomMfeParallelConstraint,
        *,
        filter_penalty: float,
    ) -> None:
        """Apply the frozen boundary policy, with whole-pool exact fallback on error."""

        proposal_count = len(optimizer.segments[0].proposal_sequences)
        try:
            report = self._refine_optimizer(
                optimizer,
                constraint,
                filter_penalty=filter_penalty,
            )
        except Exception as error:  # noqa: BLE001 - full parent fallback is mandatory
            reason = f"adaptive_boundary_error:{type(error).__name__}"
            scores = self._exact_rescore(
                optimizer,
                constraint,
                indexes=tuple(range(proposal_count)),
                reason=reason,
                prior_exact_mask=tuple(False for _ in range(proposal_count)),
            )
            optimizer._last_constraint_scores[CUSTOM_METRIC_LABELS[0]] = scores
            _recompute_custom_pool_scores(
                optimizer,
                filter_penalty=filter_penalty,
            )
            self.routing_counts["surrogate"] = 0
            self.routing_counts["full_model"] = proposal_count
            self.routing_reasons = Counter({reason: proposal_count})
            self._pending_exact_mask = tuple(True for _ in range(proposal_count))
            report = {
                "status": "full_model_fallback",
                "reason": reason,
                "boundary_budget": self.boundary_budget,
                "exact_mfe_extrema_closure": self.mfe_tail_budget > 0,
                "mfe_tail_budget": self.mfe_tail_budget,
                "initial_gate_fallbacks": None,
                "boundary_candidates": 0,
                "mfe_tail_exact_candidates": 0,
                "closure_iterations": 0,
                "exact_mfe_candidates": proposal_count,
                "selected_indexes": _accepted_top_k(optimizer, self.top_k),
                "all_selected_exact": True,
            }
        self.boundary_reports.append(report)

    def _refine_optimizer(
        self,
        optimizer: AdaptiveCustomPaperPoolOptimizer,
        constraint: _CustomMfeParallelConstraint,
        *,
        filter_penalty: float,
    ) -> dict[str, Any]:
        proposal_count = len(optimizer.segments[0].proposal_sequences)
        if len(self._pending_exact_mask) != proposal_count:
            raise RuntimeError("CUSTOM adaptive evaluator state is not proposal-aligned")
        exact_mask = list(self._pending_exact_mask)
        initial_fallbacks = sum(exact_mask)
        eligible = [
            index
            for index, outcome in enumerate(optimizer._proposal_outcomes)
            if outcome == "accepted"
        ]
        if len(eligible) < self.top_k:
            raise RuntimeError("CUSTOM adaptive boundary has fewer than top_k candidates")
        self.last_initial_ranking = tuple(
            sorted(eligible, key=lambda index: (optimizer.energy_scores[index], index))
        )
        boundary = self.last_initial_ranking[: self.boundary_budget]
        boundary_unresolved = tuple(index for index in boundary if not exact_mask[index])
        if boundary_unresolved:
            scores = self._exact_rescore(
                optimizer,
                constraint,
                indexes=boundary_unresolved,
                reason="adaptive_boundary_exact",
                prior_exact_mask=tuple(exact_mask),
            )
            optimizer._last_constraint_scores[CUSTOM_METRIC_LABELS[0]] = scores
            for index in boundary_unresolved:
                exact_mask[index] = True
            _recompute_custom_pool_scores(optimizer, filter_penalty=filter_penalty)

        iterations = 0
        tail_exact_indexes: set[int] = set()
        while True:
            iterations += 1
            if iterations > proposal_count + 1:
                raise RuntimeError("CUSTOM adaptive boundary did not reach closure")
            if self.mfe_tail_budget > 0:
                mfe_scores = optimizer._last_constraint_scores[
                    CUSTOM_METRIC_LABELS[0]
                ]
                mfe_order = sorted(
                    range(proposal_count),
                    key=lambda index: (mfe_scores[index], index),
                )
                tail_indexes = tuple(
                    dict.fromkeys(
                        (
                            *mfe_order[: self.mfe_tail_budget],
                            *mfe_order[-self.mfe_tail_budget :],
                        )
                    )
                )
                unresolved_tail = tuple(
                    index
                    for index in tail_indexes
                    if not exact_mask[index]
                )
                if unresolved_tail:
                    scores = self._exact_rescore(
                        optimizer,
                        constraint,
                        indexes=unresolved_tail,
                        reason="adaptive_mfe_tail",
                        prior_exact_mask=tuple(exact_mask),
                    )
                    optimizer._last_constraint_scores[CUSTOM_METRIC_LABELS[0]] = scores
                    for index in unresolved_tail:
                        exact_mask[index] = True
                        tail_exact_indexes.add(index)
                    _recompute_custom_pool_scores(
                        optimizer,
                        filter_penalty=filter_penalty,
                    )
                    continue
            selected = _accepted_top_k(optimizer, self.top_k)
            unresolved = tuple(index for index in selected if not exact_mask[index])
            if not unresolved:
                break
            scores = self._exact_rescore(
                optimizer,
                constraint,
                indexes=unresolved,
                reason="adaptive_boundary_closure",
                prior_exact_mask=tuple(exact_mask),
            )
            optimizer._last_constraint_scores[CUSTOM_METRIC_LABELS[0]] = scores
            for index in unresolved:
                exact_mask[index] = True
            _recompute_custom_pool_scores(optimizer, filter_penalty=filter_penalty)

        selected = _accepted_top_k(optimizer, self.top_k)
        if any(not exact_mask[index] for index in selected):
            raise RuntimeError("CUSTOM adaptive boundary returned an unvalidated candidate")
        self._pending_exact_mask = tuple(exact_mask)
        return {
            "status": "adaptive",
            "reason": None,
            "boundary_budget": self.boundary_budget,
            "exact_mfe_extrema_closure": self.mfe_tail_budget > 0,
            "mfe_tail_budget": self.mfe_tail_budget,
            "initial_gate_fallbacks": initial_fallbacks,
            "boundary_candidates": len(boundary),
            "mfe_tail_exact_candidates": len(tail_exact_indexes),
            "closure_iterations": iterations,
            "exact_mfe_candidates": sum(exact_mask),
            "selected_indexes": selected,
            "all_selected_exact": True,
        }

    def _exact_rescore(
        self,
        optimizer: AdaptiveCustomPaperPoolOptimizer,
        constraint: _CustomMfeParallelConstraint,
        *,
        indexes: tuple[int, ...],
        reason: str,
        prior_exact_mask: tuple[bool, ...],
    ) -> list[float]:
        proposal_count = len(optimizer.segments[0].proposal_sequences)
        if not indexes:
            return list(optimizer._last_constraint_scores[CUSTOM_METRIC_LABELS[0]])
        if any(index < 0 or index >= proposal_count for index in indexes):
            raise ValueError("CUSTOM adaptive boundary index is outside the pool")
        selected = set(indexes)
        mask = [index in selected for index in range(proposal_count)]
        started = perf_counter()
        try:
            dense_scores = constraint._parent.evaluate(
                mask=mask,
                verbose=optimizer.verbose,
            )
        finally:
            self.timing_seconds["full_model"] += perf_counter() - started
        scores = list(optimizer._last_constraint_scores[CUSTOM_METRIC_LABELS[0]])
        for index in indexes:
            value = float(dense_scores[index])
            if not math.isfinite(value):
                raise ValueError("CUSTOM exact boundary returned a non-finite score")
            scores[index] = value
            _annotate_exact_route(constraint, index=index, reason=reason)

        newly_exact = sum(not prior_exact_mask[index] for index in indexes)
        self.batch_counts["full_model"] += 1
        self.routing_counts["surrogate"] -= newly_exact
        self.routing_counts["full_model"] += newly_exact
        self.routing_reasons["frozen_sampled_window_mfe"] -= newly_exact
        if self.routing_reasons["frozen_sampled_window_mfe"] == 0:
            del self.routing_reasons["frozen_sampled_window_mfe"]
        self.routing_reasons[reason] += newly_exact
        return scores


class AdaptiveCustomPaperPoolOptimizer(CustomPaperPoolOptimizer):  # type: ignore[misc]
    """CUSTOM pool optimizer with an exact task-boundary refinement hook."""

    _protofuse_boundary_evaluator: AdaptiveBoundarySampledMfeEvaluator
    _protofuse_boundary_constraint: _CustomMfeParallelConstraint

    def score_energy(
        self,
        operation: Literal["add", "multiply"] = "add",
        filter_penalty: float = math.inf,
    ) -> None:
        super().score_energy(operation=operation, filter_penalty=filter_penalty)
        self._protofuse_boundary_evaluator.refine_optimizer(
            self,
            self._protofuse_boundary_constraint,
            filter_penalty=filter_penalty,
        )


def _accepted_top_k(
    optimizer: AdaptiveCustomPaperPoolOptimizer,
    top_k: int,
) -> list[int]:
    eligible = [
        index
        for index, outcome in enumerate(optimizer._proposal_outcomes)
        if outcome == "accepted"
    ]
    return sorted(
        eligible,
        key=lambda index: (optimizer.energy_scores[index], index),
    )[:top_k]


def _annotate_exact_route(
    constraint: _CustomMfeParallelConstraint,
    *,
    index: int,
    reason: str,
) -> None:
    seen: set[int] = set()
    for segment in constraint.inputs:
        sequence = segment.proposal_sequences[index]
        if id(sequence) in seen:
            continue
        seen.add(id(sequence))
        metadata = sequence._constraints_metadata[constraint.label]["data"]
        metadata.update(
            {
                "protofuse_route": "full_model",
                "protofuse_reason": reason,
            }
        )


def _recompute_custom_pool_scores(
    optimizer: AdaptiveCustomPaperPoolOptimizer,
    *,
    filter_penalty: float,
) -> None:
    metric_scores = [
        optimizer._last_constraint_scores[label] for label in CUSTOM_METRIC_LABELS
    ]
    composite = paper_composite_energies(metric_scores)
    sequences = [
        proposal.sequence for proposal in optimizer.segments[0].proposal_sequences
    ]
    optimizer.candidate_pool_sha256 = ordered_pool_sha256(sequences)
    optimizer.candidate_pool_size = len(sequences)
    optimizer.paper_energy_by_sequence = dict(zip(sequences, composite, strict=True))
    optimizer.paper_score_by_sequence = {
        sequence: 1.0 - energy
        for sequence, energy in optimizer.paper_energy_by_sequence.items()
    }
    optimizer.energy_scores = [
        score if optimizer._proposal_outcomes[index] == "accepted" else filter_penalty
        for index, score in enumerate(composite)
    ]
    optimizer._proposal_energy_scores = list(optimizer.energy_scores)
    optimizer._clear_tool_cache()


def build_adaptive_custom_mfe_bundle(
    reference_program: Program,
    *,
    workers: int = 8,
    boundary_budget: int = 20,
    top_k: int = TOP_K,
    exact_mfe_extrema: bool = False,
    mfe_tail_budget: int = 0,
) -> FusionBundle[Program]:
    """Build the frozen sampled-MFE plus exact-boundary CUSTOM fusion."""

    signature = step_group_signature(
        reference_program,
        optimizer_index=0,
        constraint_labels=(CUSTOM_METRIC_LABELS[0],),
    )

    def matches(program: Program) -> bool:
        try:
            actual = step_group_signature(
                program,
                optimizer_index=0,
                constraint_labels=(CUSTOM_METRIC_LABELS[0],),
            )
        except (TypeError, ValueError, AttributeError):
            return False
        return actual.sha256 == signature.sha256

    def apply(program: Program) -> Program:
        actual = step_group_signature(
            program,
            optimizer_index=0,
            constraint_labels=(CUSTOM_METRIC_LABELS[0],),
        )
        if actual.sha256 != signature.sha256:
            raise FusionCompatibilityError(
                "program group signature does not match adaptive CUSTOM MFE bundle"
            )
        cloned = copy.deepcopy(program)
        optimizer = cloned.optimizers[0]
        if not isinstance(optimizer, CustomPaperPoolOptimizer):
            raise FusionCompatibilityError(
                "adaptive CUSTOM MFE requires CustomPaperPoolOptimizer"
            )
        target = next(
            (
                constraint
                for constraint in optimizer.constraints
                if constraint.label == CUSTOM_METRIC_LABELS[0]
            ),
            None,
        )
        if not isinstance(target, Constraint):
            raise FusionCompatibilityError("adaptive CUSTOM MFE target is missing")
        if not target.supports_discrete or target.threshold is not None:
            raise FusionCompatibilityError(
                "adaptive CUSTOM MFE requires a discrete scoring constraint"
            )
        if target.function is None:
            raise FusionCompatibilityError("adaptive CUSTOM MFE parent is missing")
        if int(optimizer.num_results or top_k) != top_k:
            raise FusionCompatibilityError(
                "adaptive CUSTOM MFE top_k does not match optimizer num_results"
            )
        if optimizer.proposal_batch_size != optimizer.num_samples:
            raise FusionCompatibilityError(
                "adaptive CUSTOM MFE requires the complete pool in one proposal batch"
            )
        _reject_output_dependencies(cloned, 0, (target,))
        evaluator = AdaptiveBoundarySampledMfeEvaluator(
            target.function,
            target.function_config,
            workers,
            boundary_budget=boundary_budget,
            top_k=top_k,
            exact_mfe_extrema=exact_mfe_extrema,
            mfe_tail_budget=mfe_tail_budget,
        )
        replacement = _CustomMfeParallelConstraint(parent=target, evaluator=evaluator)
        optimizer.constraints = [
            replacement if constraint is target else constraint
            for constraint in optimizer.constraints
        ]
        optimizer.__class__ = AdaptiveCustomPaperPoolOptimizer
        adaptive_optimizer = cast(AdaptiveCustomPaperPoolOptimizer, optimizer)
        adaptive_optimizer._protofuse_boundary_evaluator = evaluator
        adaptive_optimizer._protofuse_boundary_constraint = replacement
        dynamic_program = cast(Any, cloned)
        dynamic_program._protofuse_evaluators = [evaluator]
        dynamic_program._protofuse_validation_work = [Counter()]
        dynamic_program._protofuse_adaptive_boundary = {
            "source": "sampled",
            "boundary_budget": boundary_budget,
            "top_k": top_k,
            "exact_mfe_extrema_closure": (
                exact_mfe_extrema or mfe_tail_budget > 0
            ),
            "mfe_tail_budget": max(mfe_tail_budget, int(exact_mfe_extrema)),
            "selected_candidates_exactly_rescored": True,
        }
        cloned._validate_program()
        return cloned

    return FusionBundle(
        fusion_id="custom-mfe-adaptive-boundary",
        version=(
            f"sampled-top-{boundary_budget}-tail-"
            f"{max(mfe_tail_budget, int(exact_mfe_extrema))}-v3"
            if exact_mfe_extrema or mfe_tail_budget > 0
            else f"sampled-top-{boundary_budget}-v1"
        ),
        matches=matches,
        apply=apply,
    )


@dataclass(frozen=True)
class BoundaryGates:
    """Predeclared task-level gates for an adaptive policy."""

    min_mean_top10_recall: float = 1.0
    min_seed_top10_recall: float = 1.0
    min_mfe_work_avoided_fraction: float = 0.50

    def as_dict(self) -> dict[str, float]:
        return {
            "min_mean_top10_recall": self.min_mean_top10_recall,
            "min_seed_top10_recall": self.min_seed_top10_recall,
            "min_mfe_work_avoided_fraction": self.min_mfe_work_avoided_fraction,
        }


DEFAULT_BOUNDARY_GATES = BoundaryGates()


@dataclass(frozen=True)
class CustomPool:
    """One complete ordered CUSTOM pool reconstructed from a teacher trace."""

    group_id: str
    input_hashes: tuple[str, ...]
    metric_scores: np.ndarray
    filter_pass: np.ndarray


@dataclass(frozen=True)
class ApproximateMfe:
    """One frozen approximate MFE score and applicability decision per candidate."""

    source: Literal["sampled", "ridge_residual"]
    scores_by_hash: dict[str, float]
    accepted_by_hash: dict[str, bool]
    rejection_reason_by_hash: dict[str, str]


def load_custom_pools(
    trace_paths: Sequence[Path],
    *,
    expected_groups: set[str],
    expected_pool_size: int = 1000,
) -> tuple[CustomPool, ...]:
    """Reconstruct exact metric matrices with strict per-proposal alignment."""

    pools: list[CustomPool] = []
    seen_groups: set[str] = set()
    for path in trace_paths:
        rows = tuple(_read_trace(path.resolve()))
        groups = {row.group_id for row in rows}
        if len(groups) != 1:
            raise ValueError(f"{path} must contain exactly one CUSTOM pool group")
        group_id = next(iter(groups))
        if group_id not in expected_groups:
            raise ValueError(f"trace group {group_id!r} is outside the declared cohort")
        if group_id in seen_groups:
            raise ValueError(f"trace group {group_id!r} appears more than once")
        seen_groups.add(group_id)
        by_label = {
            label: sorted(
                (
                    row
                    for row in rows
                    if row.optimizer_index == 0 and row.constraint_label == label
                ),
                key=lambda row: row.proposal_index,
            )
            for label in (*CUSTOM_METRIC_LABELS, "homopolymer_filter")
        }
        for label, label_rows in by_label.items():
            if len(label_rows) != expected_pool_size:
                raise ValueError(
                    f"{path} has {len(label_rows)} {label!r} rows; "
                    f"expected {expected_pool_size}"
                )
            if [row.proposal_index for row in label_rows] != list(
                range(expected_pool_size)
            ):
                raise ValueError(f"{path} has misaligned {label!r} proposal indexes")
            if any(
                row.error is not None
                or row.score is None
                or not math.isfinite(float(row.score))
                for row in label_rows
            ):
                raise ValueError(f"{path} has incomplete {label!r} rows")
        input_hashes = tuple(row.input_sha256[0] for row in by_label["custom_mfe"])
        for label_rows in by_label.values():
            if tuple(row.input_sha256[0] for row in label_rows) != input_hashes:
                raise ValueError(f"{path} constraint inputs are not proposal-aligned")
        metric_rows: list[list[float]] = [
            [float(cast(float, row.score)) for row in by_label[label]]
            for label in CUSTOM_METRIC_LABELS
        ]
        metric_scores = np.asarray(metric_rows, dtype=np.float64)
        filter_pass = np.asarray(
            [
                float(cast(float, row.score))
                <= float(cast(float, row.constraint_threshold))
                for row in by_label["homopolymer_filter"]
            ],
            dtype=np.bool_,
        )
        pools.append(
            CustomPool(
                group_id=group_id,
                input_hashes=input_hashes,
                metric_scores=metric_scores,
                filter_pass=filter_pass,
            )
        )
    missing = sorted(expected_groups - seen_groups)
    if missing:
        raise ValueError(f"CUSTOM boundary cohort is missing groups: {missing}")
    return tuple(sorted(pools, key=lambda pool: pool.group_id))


def _raw_mfe_to_constraint_score(raw_mfe: np.ndarray) -> np.ndarray:
    scores = (raw_mfe + 200.0) / 200.0
    if not np.all(np.isfinite(scores)):
        raise ValueError("CUSTOM boundary predictions contain non-finite MFE")
    return scores


def approximate_mfe_views(
    dataset: ResidualDataset,
    candidate: FittedResidualCandidate,
) -> tuple[ApproximateMfe, ApproximateMfe]:
    """Build the two frozen approximation views without consulting exact audit labels."""

    hashes = [str(value) for value in dataset.input_hashes]
    baseline_scores = _raw_mfe_to_constraint_score(dataset.baseline)
    baseline_accepted = (
        np.isfinite(dataset.baseline)
        & np.isfinite(dataset.baseline_uncertainty)
        & (
            dataset.baseline_uncertainty
            <= FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
        )
    )
    sampled_reasons = {
        input_hash: "sampled_mfe_uncertain"
        for input_hash, accepted in zip(hashes, baseline_accepted, strict=True)
        if not accepted
    }

    members = candidate.member_predictions(dataset.features)
    residual_prediction = members.mean(axis=0)
    model_uncertainty = members.std(axis=0)
    support = _support_scores(
        dataset.features,
        candidate.support_center,
        candidate.support_scale,
    )
    residual_raw = dataset.baseline + residual_prediction
    residual_scores = _raw_mfe_to_constraint_score(residual_raw)
    residual_accepted = (
        baseline_accepted
        & np.isfinite(model_uncertainty)
        & np.isfinite(support)
        & (model_uncertainty <= candidate.uncertainty_threshold)
        & (support <= candidate.support_threshold)
    )
    residual_reasons: dict[str, str] = {}
    for index, input_hash in enumerate(hashes):
        if residual_accepted[index]:
            continue
        if not baseline_accepted[index]:
            reason = "residual_mfe_baseline_uncertain"
        elif support[index] > candidate.support_threshold:
            reason = "residual_mfe_out_of_domain"
        else:
            reason = "residual_mfe_model_uncertain"
        residual_reasons[input_hash] = reason

    return (
        ApproximateMfe(
            source="sampled",
            scores_by_hash=dict(zip(hashes, baseline_scores.tolist(), strict=True)),
            accepted_by_hash=dict(zip(hashes, baseline_accepted.tolist(), strict=True)),
            rejection_reason_by_hash=sampled_reasons,
        ),
        ApproximateMfe(
            source="ridge_residual",
            scores_by_hash=dict(zip(hashes, residual_scores.tolist(), strict=True)),
            accepted_by_hash=dict(zip(hashes, residual_accepted.tolist(), strict=True)),
            rejection_reason_by_hash=residual_reasons,
        ),
    )


def _rank_top_k(
    metric_scores: np.ndarray,
    filter_pass: np.ndarray,
    *,
    top_k: int,
) -> tuple[int, ...]:
    energies = paper_composite_energies(metric_scores.tolist())
    eligible = [index for index, passed in enumerate(filter_pass) if passed]
    return tuple(sorted(eligible, key=lambda index: (energies[index], index))[:top_k])


def simulate_adaptive_pool(
    pool: CustomPool,
    approximation: ApproximateMfe,
    *,
    boundary_budget: int,
    top_k: int = TOP_K,
    exact_mfe_extrema: bool = False,
    mfe_tail_budget: int = 0,
) -> dict[str, Any]:
    """Exact a provisional boundary and optionally close pool-normalization extrema."""

    if boundary_budget < top_k:
        raise ValueError("CUSTOM boundary budget must be at least top_k")
    if mfe_tail_budget < 0:
        raise ValueError("CUSTOM MFE tail budget must be non-negative")
    resolved_tail_budget = max(mfe_tail_budget, int(exact_mfe_extrema))
    exact_mfe = pool.metric_scores[0]
    predicted_mfe = np.asarray(
        [approximation.scores_by_hash[value] for value in pool.input_hashes],
        dtype=np.float64,
    )
    accepted = np.asarray(
        [approximation.accepted_by_hash[value] for value in pool.input_hashes],
        dtype=np.bool_,
    )
    exact_mask = ~accepted
    initial_scores = pool.metric_scores.copy()
    initial_scores[0] = np.where(exact_mask, exact_mfe, predicted_mfe)
    initial_energies = paper_composite_energies(initial_scores.tolist())
    eligible = [index for index, passed in enumerate(pool.filter_pass) if passed]
    boundary = sorted(
        eligible,
        key=lambda index: (initial_energies[index], index),
    )[:boundary_budget]
    exact_mask[boundary] = True

    iterations = 0
    tail_exact_indexes: set[int] = set()
    while True:
        iterations += 1
        if iterations > len(pool.input_hashes) + 1:
            raise RuntimeError("CUSTOM adaptive boundary did not reach closure")
        mixed_scores = pool.metric_scores.copy()
        mixed_scores[0] = np.where(exact_mask, exact_mfe, predicted_mfe)
        if resolved_tail_budget > 0:
            mfe_order = np.argsort(mixed_scores[0], kind="stable").tolist()
            tail_indexes = tuple(
                dict.fromkeys(
                    (
                        *mfe_order[:resolved_tail_budget],
                        *mfe_order[-resolved_tail_budget:],
                    )
                )
            )
            unresolved_tail = [
                index
                for index in tail_indexes
                if not exact_mask[index]
            ]
            if unresolved_tail:
                exact_mask[unresolved_tail] = True
                tail_exact_indexes.update(unresolved_tail)
                continue
        selected = _rank_top_k(mixed_scores, pool.filter_pass, top_k=top_k)
        unresolved = [index for index in selected if not exact_mask[index]]
        if not unresolved:
            break
        exact_mask[unresolved] = True

    exact_selected = _rank_top_k(pool.metric_scores, pool.filter_pass, top_k=top_k)
    recall = len(set(selected) & set(exact_selected)) / len(set(exact_selected))
    exact_count = int(exact_mask.sum())
    sampled_window_work = len(pool.input_hashes) * EXPECTED_WINDOWS
    exact_window_work = exact_count * FULL_WINDOWS_PER_SEQUENCE
    total_window_work = sampled_window_work + exact_window_work
    full_window_work = len(pool.input_hashes) * FULL_WINDOWS_PER_SEQUENCE
    rejection_reasons: dict[str, int] = {}
    for index, input_hash in enumerate(pool.input_hashes):
        if accepted[index]:
            continue
        reason = approximation.rejection_reason_by_hash[input_hash]
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    return {
        "group_id": pool.group_id,
        "source": approximation.source,
        "boundary_budget": boundary_budget,
        "exact_mfe_extrema_closure": resolved_tail_budget > 0,
        "mfe_tail_budget": resolved_tail_budget,
        "top10_recall": recall,
        "ordered_top10_identical": selected == exact_selected,
        "selected_indexes": list(selected),
        "exact_selected_indexes": list(exact_selected),
        "exact_mfe_candidates": exact_count,
        "initial_gate_fallbacks": int((~accepted).sum()),
        "boundary_candidates": len(boundary),
        "mfe_tail_exact_candidates": len(tail_exact_indexes),
        "closure_iterations": iterations,
        "mfe_window_work": total_window_work,
        "full_mfe_window_work": full_window_work,
        "mfe_work_avoided_fraction": 1.0 - total_window_work / full_window_work,
        "theoretical_mfe_speedup": full_window_work / total_window_work,
        "rejection_reasons": rejection_reasons,
    }


def aggregate_boundary_runs(
    runs: Sequence[dict[str, Any]],
    *,
    gates: BoundaryGates = DEFAULT_BOUNDARY_GATES,
) -> dict[str, Any]:
    """Aggregate one source/budget policy across complete independent pools."""

    if not runs:
        raise ValueError("CUSTOM boundary aggregation requires runs")
    recalls = np.asarray([run["top10_recall"] for run in runs], dtype=np.float64)
    avoided = np.asarray(
        [run["mfe_work_avoided_fraction"] for run in runs], dtype=np.float64
    )
    exact_counts = np.asarray(
        [run["exact_mfe_candidates"] for run in runs], dtype=np.float64
    )
    checks = {
        "mean_top10_recall": float(recalls.mean()) >= gates.min_mean_top10_recall,
        "minimum_top10_recall": float(recalls.min()) >= gates.min_seed_top10_recall,
        "mfe_work_avoided": (
            float(avoided.mean()) >= gates.min_mfe_work_avoided_fraction
        ),
    }
    return {
        "source": runs[0]["source"],
        "boundary_budget": runs[0]["boundary_budget"],
        "exact_mfe_extrema_closure": runs[0]["exact_mfe_extrema_closure"],
        "mfe_tail_budget": runs[0]["mfe_tail_budget"],
        "pool_count": len(runs),
        "mean_top10_recall": float(recalls.mean()),
        "minimum_top10_recall": float(recalls.min()),
        "ordered_top10_identical_pools": sum(
            bool(run["ordered_top10_identical"]) for run in runs
        ),
        "mean_exact_mfe_candidates": float(exact_counts.mean()),
        "maximum_exact_mfe_candidates": int(exact_counts.max()),
        "mean_mfe_work_avoided_fraction": float(avoided.mean()),
        "mean_theoretical_mfe_speedup": float(
            np.mean([run["theoretical_mfe_speedup"] for run in runs])
        ),
        "checks": checks,
        "passed": all(checks.values()),
        "runs": list(runs),
    }


def select_boundary_policy(
    policies: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """Choose least exact work; prefer the simpler sampled source on an exact tie."""

    eligible = [policy for policy in policies if policy["passed"]]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda policy: (
            policy["mean_exact_mfe_candidates"],
            0 if policy["source"] == "sampled" else 1,
            policy["boundary_budget"],
        ),
    )
