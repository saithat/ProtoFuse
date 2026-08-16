"""Exact matching and transactional Proto constraint-group transformation."""

from __future__ import annotations

import copy
import functools
import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, cast

from proto_language.core import Constraint, ConstraintOutput, Program
from proto_language.core import Sequence as ProtoSequence
from proto_language.core.optimizer import derive_seeds
from proto_language.optimizer import RejectionSamplingOptimizer, RejectionSamplingOptimizerConfig

from protofuse.sai.exact_custom import (
    FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL,
    ExactCustomMfeEvaluator,
    SampledCustomMfeEvaluator,
)
from protofuse.sai.model import LinearEnsembleModel, LinearEnsemblePredictor
from protofuse.sai.registry import FusionBundle
from protofuse.sai.router import (
    BatchSelectiveRouter,
    GateDecision,
    RoutedResult,
    SurrogatePrediction,
)
from protofuse.sai.signatures import step_group_signature


class FusionCompatibilityError(ValueError):
    """Raised when an artifact cannot safely replace the requested component group."""


InputItem = tuple[ProtoSequence, ...]
ObjectiveOutputs = tuple[ConstraintOutput, ...]


def linear_gate_decision(
    model: LinearEnsembleModel,
    *,
    values: Sequence[float],
    uncertainties: Sequence[float],
    support_score: object,
) -> GateDecision:
    """Apply the runtime's exact frozen-model acceptance gate."""

    if isinstance(support_score, bool) or not isinstance(support_score, (int, float)):
        return GateDecision(False, "invalid_support_score")
    resolved_support = float(support_score)
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
        return GateDecision(False, "prediction_out_of_range")
    if not math.isfinite(resolved_support):
        return GateDecision(False, "invalid_support_score")
    if any(not math.isfinite(value) for value in uncertainties):
        return GateDecision(False, "invalid_uncertainty")
    if resolved_support > model.support_threshold:
        return GateDecision(False, "out_of_domain")
    if max(uncertainties, default=0.0) > model.uncertainty_threshold:
        return GateDecision(False, "uncertain")
    return GateDecision(True, "calibrated_in_domain")


def _structure_key(sequence: ProtoSequence) -> str | None:
    structure = getattr(sequence, "structure", None)
    text = getattr(structure, "structure", None)
    return sha256(text.encode()).hexdigest() if isinstance(text, str) else None


def _batch_key(items: Sequence[InputItem]) -> tuple[tuple[tuple[str, str | None], ...], ...]:
    return tuple(
        tuple((str(sequence.sequence), _structure_key(sequence)) for sequence in item)
        for item in items
    )


@dataclass
class _OriginalObjective:
    label: str
    constraint: Constraint


class _ConstraintGroupEvaluator:
    """Route one vector prediction while preserving several ordinary constraints.

    Jointness here is operational: one prediction and one fail-closed route for the group. The
    objectives are not scalarized, and the current linear model is not covariance-aware.
    """

    def __init__(
        self,
        *,
        objectives: Sequence[_OriginalObjective],
        model: LinearEnsembleModel,
    ) -> None:
        self.objectives = tuple(objectives)
        self.predictor = LinearEnsemblePredictor(model)
        self.model = model
        self._cache_key: tuple[tuple[tuple[str, str | None], ...], ...] | None = None
        self._cache: dict[str, list[ConstraintOutput]] = {}
        self._remaining: set[str] = set()
        self.routing_counts = {"surrogate": 0, "full_model": 0}
        self.routing_reasons: Counter[str] = Counter()
        self.timing_seconds = {"surrogate": 0.0, "gate": 0.0, "full_model": 0.0}
        self.router = BatchSelectiveRouter[InputItem, ObjectiveOutputs](
            surrogate=self._surrogate,
            gate=self._gate,
            full_model=self._full_model,
        )

    def _surrogate(
        self,
        items: Sequence[InputItem],
    ) -> list[SurrogatePrediction[ObjectiveOutputs]]:
        started = perf_counter()
        try:
            predictions: list[SurrogatePrediction[ObjectiveOutputs]] = []
            for item in items:
                prediction = self.predictor.predict(
                    tuple(str(sequence.sequence) for sequence in item)
                )
                outputs = tuple(
                    ConstraintOutput(
                        score=value,
                        metadata={
                            "protofuse_predicted_score": value,
                            "protofuse_uncertainty": prediction.uncertainties[index],
                            "protofuse_support_score": prediction.support_score,
                        },
                    )
                    for index, value in enumerate(prediction.values)
                )
                predictions.append(
                    SurrogatePrediction(
                        outputs,
                        {
                            "values": prediction.values,
                            "uncertainties": prediction.uncertainties,
                            "support_score": prediction.support_score,
                        },
                    )
                )
            return predictions
        finally:
            self.timing_seconds["surrogate"] += perf_counter() - started

    def _gate(
        self,
        _item: InputItem,
        prediction: SurrogatePrediction[ObjectiveOutputs],
    ) -> GateDecision:
        started = perf_counter()
        try:
            values = cast(tuple[float, ...], prediction.metadata["values"])
            uncertainties = cast(tuple[float, ...], prediction.metadata["uncertainties"])
            support_value = prediction.metadata["support_score"]
            return linear_gate_decision(
                self.model,
                values=values,
                uncertainties=uncertainties,
                support_score=support_value,
            )
        finally:
            self.timing_seconds["gate"] += perf_counter() - started

    def _full_model(self, items: Sequence[InputItem]) -> list[ObjectiveOutputs]:
        started = perf_counter()
        try:
            per_objective: list[list[ConstraintOutput]] = []
            input_list = list(items)
            for objective in self.objectives:
                parent = objective.constraint
                function = parent.function
                if function is None:
                    raise FusionCompatibilityError(
                        f"parent objective {objective.label!r} is missing its function"
                    )
                outputs = list(function(input_list, config=parent.function_config))
                if len(outputs) != len(items):
                    raise ValueError(
                        f"parent objective {objective.label!r} returned {len(outputs)} outputs "
                        f"for {len(items)} inputs"
                    )
                if any(not isinstance(output, ConstraintOutput) for output in outputs):
                    raise TypeError(
                        f"parent objective {objective.label!r} returned an invalid output"
                    )
                per_objective.append(outputs)
            return [
                tuple(outputs[item_index] for outputs in per_objective)
                for item_index in range(len(items))
            ]
        finally:
            self.timing_seconds["full_model"] += perf_counter() - started

    def evaluate(self, label: str, items: list[InputItem]) -> list[ConstraintOutput]:
        key = _batch_key(items)
        if self._cache_key != key or label not in self._remaining:
            routed = self.router(items)
            for result in routed:
                self.routing_counts[result.route] += 1
                self.routing_reasons[result.reason] += 1
            self._cache_key = key
            self._remaining = {objective.label for objective in self.objectives}
            self._cache = {
                objective.label: [self._with_route(result, objective_index) for result in routed]
                for objective_index, objective in enumerate(self.objectives)
            }
        try:
            outputs = self._cache[label]
        except KeyError as exc:
            raise FusionCompatibilityError(f"unknown routed objective {label!r}") from exc
        self._remaining.discard(label)
        if not self._remaining:
            self._cache_key = None
            self._cache = {}
        return outputs

    @staticmethod
    def _with_route(
        routed: RoutedResult[ObjectiveOutputs],
        objective_index: int,
    ) -> ConstraintOutput:
        output = routed.value[objective_index]
        metadata = {
            **output.metadata,
            "protofuse_route": routed.route,
            "protofuse_reason": routed.reason,
        }
        return output.model_copy(update={"metadata": metadata})


def _proxy_function(
    evaluator: _ConstraintGroupEvaluator,
    label: str,
) -> Any:
    def routed_constraint(
        input_sequences: list[InputItem],
        config: Any,
    ) -> list[ConstraintOutput]:
        del config
        return evaluator.evaluate(label, input_sequences)

    routed_constraint.__name__ = f"protofuse_{label}_constraint"
    return routed_constraint


class _RoutedConstraint(Constraint):
    """Mirror optimizer seed propagation onto the retained parent objective."""

    def __init__(
        self,
        *,
        parent: Constraint,
        evaluator: _ConstraintGroupEvaluator,
        seed_config: dict[str, int | None],
    ) -> None:
        function = _proxy_function(evaluator, parent.label)
        if bool(getattr(parent.function, "_constraint_allow_raw_scores", False)):
            function._constraint_allow_raw_scores = True
        super().__init__(
            inputs=parent.inputs,
            function=function,
            function_config=seed_config,
            label=parent.label,
            weight=parent.weight,
        )
        self._parent = parent

    def _set_program_seed(self, seed: int | None) -> None:
        super()._set_program_seed(seed)
        self._parent._set_program_seed(seed)


class _CustomMfeParallelConstraint(Constraint):
    """Retain the original constraint contract while changing only its executor."""

    def __init__(self, *, parent: Constraint, evaluator: Any) -> None:
        original_function = parent.function
        if original_function is None:
            raise FusionCompatibilityError("CUSTOM MFE target is missing its parent function")

        @functools.wraps(original_function)
        def parallel_function(input_sequences: list[InputItem], config: Any) -> Any:
            return evaluator.evaluate(input_sequences, config)

        if bool(getattr(original_function, "_constraint_allow_raw_scores", False)):
            cast(Any, parallel_function)._constraint_allow_raw_scores = True
        super().__init__(
            inputs=parent.inputs,
            function=parallel_function,
            function_config=copy.deepcopy(parent.function_config),
            label=parent.label,
            weight=parent.weight,
        )
        self._parent = parent

    def _set_program_seed(self, seed: int | None) -> None:
        super()._set_program_seed(seed)
        self._parent._set_program_seed(seed)


class _ValidationConstraint(Constraint):
    """Reproduce the original optimizer's child seed in the validation stage."""

    def __init__(
        self,
        constraint: Constraint,
        *,
        source_optimizer: Any,
        constraint_index: int,
        work_counter: Counter[str],
    ) -> None:
        original_function = constraint.function
        if original_function is None:
            raise FusionCompatibilityError(
                f"final validation cannot evaluate constraint {constraint.label!r}"
            )

        @functools.wraps(original_function)
        def validation_function(input_sequences: list[InputItem], config: Any) -> Any:
            work_counter["parent_item_evaluations"] += len(input_sequences)
            return original_function(input_sequences, config=config)

        if bool(getattr(original_function, "_constraint_allow_raw_scores", False)):
            cast(Any, validation_function)._constraint_allow_raw_scores = True
        super().__init__(
            inputs=constraint.inputs,
            function=validation_function,
            function_config=copy.deepcopy(constraint.function_config),
            backward=constraint.backward,
            backward_config=copy.deepcopy(constraint.backward_config),
            label=constraint.label,
            threshold=constraint.threshold,
            weight=None if constraint.threshold is not None else constraint.weight,
            input_slots=copy.deepcopy(getattr(constraint, "_input_slots", [])),
            gradient_positions=constraint.gradient_positions,
        )
        self._source_optimizer = source_optimizer
        self._source_constraint_index = constraint_index

    def _set_program_seed(self, seed: int | None) -> None:
        del seed
        source_seed = self._source_optimizer.seed
        if source_seed is None:
            super()._set_program_seed(None)
            return
        generator_count = len(self._source_optimizer.generators)
        constraint_count = len(self._source_optimizer.constraints)
        original_seeds = derive_seeds(source_seed, generator_count + constraint_count)
        super()._set_program_seed(original_seeds[generator_count + self._source_constraint_index])


def _clone_constraint(
    constraint: Constraint,
    *,
    source_optimizer: Any,
    constraint_index: int,
    work_counter: Counter[str],
) -> Constraint:
    """Clone a constraint while retaining the cloned program's segment identities."""

    if not constraint.supports_discrete:
        raise FusionCompatibilityError(
            f"final validation cannot discretely evaluate constraint {constraint.label!r}"
        )
    return _ValidationConstraint(
        constraint,
        source_optimizer=source_optimizer,
        constraint_index=constraint_index,
        work_counter=work_counter,
    )


def _reject_output_dependencies(
    program: Program,
    optimizer_index: int,
    targets: Sequence[Any],
) -> None:
    target_segment_ids = {id(segment) for target in targets for segment in target.inputs}
    target_ids = {id(target) for target in targets}
    for later_index, optimizer in enumerate(
        program.optimizers[optimizer_index:],
        start=optimizer_index,
    ):
        for constraint in optimizer.constraints:
            if id(constraint) in target_ids:
                continue
            for slot, segment in zip(
                getattr(constraint, "_input_slots", ()),
                constraint.inputs,
                strict=False,
            ):
                if id(segment) in target_segment_ids and (
                    slot.requires_structure or slot.requires_logits
                ):
                    raise FusionCompatibilityError(
                        f"constraint {constraint.label!r} in optimizer {later_index} requires "
                        "structure/logits produced by the target group"
                    )


def _append_final_validation(
    program: Program,
    *,
    optimizer_index: int,
    source_optimizer: Any,
) -> Counter[str]:
    result_count = int(source_optimizer.num_results or program.num_results)
    validation_work = Counter[str]()
    validation_constraints = [
        _clone_constraint(
            constraint,
            source_optimizer=source_optimizer,
            constraint_index=index,
            work_counter=validation_work,
        )
        for index, constraint in enumerate(source_optimizer.constraints)
    ]
    validation = RejectionSamplingOptimizer(
        constructs=source_optimizer.constructs,
        generators=[],
        constraints=validation_constraints,
        config=RejectionSamplingOptimizerConfig(
            num_samples=result_count,
            num_results=result_count,
            proposal_source="existing_results",
            proposal_batch_size=result_count,
            seed=source_optimizer.seed,
        ),
    )
    program.optimizers.insert(optimizer_index + 1, validation)
    return validation_work


def transform_with_artifact(program: Program, artifact: Any) -> Program:
    """Return a transformed deep copy or raise before touching the original."""

    manifest = artifact.manifest
    actual = step_group_signature(
        program,
        optimizer_index=manifest.optimizer_index,
        constraint_labels=manifest.constraint_labels,
    )
    if actual.sha256 != manifest.group_signature_sha256:
        raise FusionCompatibilityError("program group signature does not match fusion artifact")
    if not manifest.final_validation_required or not manifest.score_only:
        raise FusionCompatibilityError(
            "only score-only fusions with final validation are supported"
        )

    cloned = copy.deepcopy(program)
    optimizer = cloned.optimizers[manifest.optimizer_index]
    by_label = {constraint.label: constraint for constraint in optimizer.constraints}
    targets = [by_label[label] for label in manifest.constraint_labels]
    if any(not target.supports_discrete or target.threshold is not None for target in targets):
        raise FusionCompatibilityError("fusion targets must be discrete scoring constraints")
    input_ids = tuple(id(segment) for segment in targets[0].inputs)
    if any(tuple(id(segment) for segment in target.inputs) != input_ids for target in targets):
        raise FusionCompatibilityError("joint fusion constraints must share identical inputs")
    if any(
        slot.requires_structure or slot.requires_logits
        for target in targets
        for slot in getattr(target, "_input_slots", ())
    ):
        raise FusionCompatibilityError("sequence-only model cannot consume structure or logits")
    _reject_output_dependencies(cloned, manifest.optimizer_index, targets)

    originals = [_OriginalObjective(target.label, target) for target in targets]
    if any(objective.constraint.function is None for objective in originals):
        raise FusionCompatibilityError("target constraint is missing its parent function")
    seed_configs: dict[str, dict[str, int | None]] = {
        target.label: {"seed": None} for target in targets
    }
    evaluator = _ConstraintGroupEvaluator(
        objectives=originals,
        model=artifact.model,
    )
    target_ids = {id(target) for target in targets}
    replacements: dict[str, Constraint] = {
        target.label: _RoutedConstraint(
            parent=target,
            evaluator=evaluator,
            seed_config=seed_configs[target.label],
        )
        for target in targets
    }
    new_constraints = [
        replacements[constraint.label] if id(constraint) in target_ids else constraint
        for constraint in optimizer.constraints
    ]

    validation_work = _append_final_validation(
        cloned,
        optimizer_index=manifest.optimizer_index,
        source_optimizer=optimizer,
    )

    optimizer.constraints = new_constraints
    dynamic_program = cast(Any, cloned)
    dynamic_program._protofuse_evaluators = [evaluator]
    dynamic_program._protofuse_validation_work = [validation_work]
    cloned._validate_program()
    return cloned


def _transform_custom_mfe_executor(
    program: Program,
    *,
    expected_signature_sha256: str,
    evaluator_factory: Callable[[Any, Any], Any],
    sampled: bool,
) -> Program:
    labels = ("custom_mfe",)
    actual = step_group_signature(
        program,
        optimizer_index=0,
        constraint_labels=labels,
    )
    if actual.sha256 != expected_signature_sha256:
        raise FusionCompatibilityError("program group signature does not match CUSTOM MFE bundle")

    cloned = copy.deepcopy(program)
    optimizer = cloned.optimizers[0]
    by_label = {constraint.label: constraint for constraint in optimizer.constraints}
    target = by_label[labels[0]]
    if not target.supports_discrete or target.threshold is not None:
        raise FusionCompatibilityError("CUSTOM MFE fusion requires a discrete scoring constraint")
    _reject_output_dependencies(cloned, 0, (target,))
    if target.function is None:
        raise FusionCompatibilityError("CUSTOM MFE target is missing its parent function")

    evaluator = evaluator_factory(target.function, target.function_config)
    replacement = _CustomMfeParallelConstraint(parent=target, evaluator=evaluator)
    validation_work = Counter[str]()
    if sampled:
        validation_work = _append_final_validation(
            cloned,
            optimizer_index=0,
            source_optimizer=optimizer,
        )
    optimizer.constraints = [
        replacement if constraint is target else constraint
        for constraint in optimizer.constraints
    ]
    dynamic_program = cast(Any, cloned)
    if sampled:
        dynamic_program._protofuse_evaluators = [evaluator]
    else:
        dynamic_program._protofuse_exact_evaluators = [evaluator]
    dynamic_program._protofuse_validation_work = [validation_work]
    cloned._validate_program()
    return cloned


def build_exact_custom_mfe_bundle(
    reference_program: Program,
    *,
    workers: int = 8,
) -> FusionBundle[Program]:
    """Build the bit-identical ordered-process CUSTOM MFE bundle."""

    signature = step_group_signature(
        reference_program,
        optimizer_index=0,
        constraint_labels=("custom_mfe",),
    )

    def matches(program: Program) -> bool:
        try:
            actual = step_group_signature(
                program,
                optimizer_index=0,
                constraint_labels=("custom_mfe",),
            )
        except (TypeError, ValueError, AttributeError):
            return False
        return actual.sha256 == signature.sha256

    def apply(program: Program) -> Program:
        return _transform_custom_mfe_executor(
            program,
            expected_signature_sha256=signature.sha256,
            evaluator_factory=lambda function, config: ExactCustomMfeEvaluator(
                function,
                config,
                workers,
            ),
            sampled=False,
        )

    return FusionBundle(
        fusion_id="custom-mfe-exact-parallel",
        version=f"workers-{workers}",
        matches=matches,
        apply=apply,
    )


def build_sampled_custom_mfe_bundle(
    reference_program: Program,
    *,
    workers: int,
    window_stride: int,
    intercept: float,
    slope: float,
    uncertainty_threshold: float = (
        FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
    ),
) -> FusionBundle[Program]:
    """Build a frozen fixed-stride CUSTOM MFE approximation bundle."""

    signature = step_group_signature(
        reference_program,
        optimizer_index=0,
        constraint_labels=("custom_mfe",),
    )

    def matches(program: Program) -> bool:
        try:
            actual = step_group_signature(
                program,
                optimizer_index=0,
                constraint_labels=("custom_mfe",),
            )
        except (TypeError, ValueError, AttributeError):
            return False
        return actual.sha256 == signature.sha256

    def apply(program: Program) -> Program:
        return _transform_custom_mfe_executor(
            program,
            expected_signature_sha256=signature.sha256,
            evaluator_factory=lambda function, config: SampledCustomMfeEvaluator(
                function,
                config,
                workers,
                window_stride=window_stride,
                intercept=intercept,
                slope=slope,
                uncertainty_threshold=uncertainty_threshold,
            ),
            sampled=True,
        )

    return FusionBundle(
        fusion_id="custom-mfe-sampled-window",
        version=f"stride-{window_stride}-uncertainty-q99-v1",
        matches=matches,
        apply=apply,
    )


def build_artifact_bundle(artifact: Any) -> FusionBundle[object]:
    manifest = artifact.manifest

    def matches(program: object) -> bool:
        if not isinstance(program, Program):
            return False
        try:
            actual = step_group_signature(
                program,
                optimizer_index=manifest.optimizer_index,
                constraint_labels=manifest.constraint_labels,
            )
        except (TypeError, ValueError, AttributeError):
            return False
        return bool(actual.sha256 == manifest.group_signature_sha256)

    def apply(program: object) -> object:
        if not isinstance(program, Program):
            raise FusionCompatibilityError("artifact bundle requires a Proto Program")
        return transform_with_artifact(program, artifact)

    return FusionBundle(
        fusion_id=manifest.fusion_id,
        version=manifest.version,
        matches=matches,
        apply=apply,
    )
