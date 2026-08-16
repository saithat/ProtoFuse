"""One readable experiment: warm up, run paired arms, report every metric."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Literal

from proto_language.core import Program
from proto_language.core.optimizer import derive_seeds

from protofuse.execution_context import program_execution_scope
from protofuse.sai.evaluation_report import aggregate_paired_runs
from protofuse.sai.hardware import (
    ExperimentHardware,
    experiment_hardware,
    pinned_modal_hardware,
)
from protofuse.sai.transform import transform_with_artifact

Arm = Literal["full", "fused"]
EnergyKind = Literal["finite", "positive_infinity", "negative_infinity", "nan"]
RunStatus = Literal[
    "ok",
    "arm_failed",
    "candidate_pool_mismatch",
    "output_length_mismatch",
    "non_finite_energy",
]


@dataclass(frozen=True)
class ProgramOutputs:
    sequences: tuple[str, ...]
    energies: tuple[float, ...]
    result_metadata: tuple[dict[str, Any], ...] = ()
    energy_comparable: bool = True
    energy_comparison_reason: str | None = None
    candidate_pool_sha256: str | None = None
    candidate_pool_size: int | None = None


@dataclass(frozen=True)
class ArmExecution:
    seconds: float
    outputs: ProgramOutputs | None
    error_type: str | None


@dataclass(frozen=True)
class WarmupReport:
    seed: int
    order: tuple[Arm, Arm]
    full_seconds: float
    fused_seconds: float
    full_error_type: str | None
    fused_error_type: str | None
    excluded_from_primary_timing: bool = True


@dataclass(frozen=True)
class PairedRun:
    seed: int
    order: tuple[Arm, Arm]
    status: RunStatus
    full_seconds: float
    fused_seconds: float
    speedup: float | None
    full_error_type: str | None
    fused_error_type: str | None
    full_sequences: tuple[str, ...]
    fused_sequences: tuple[str, ...]
    full_result_metadata: tuple[dict[str, Any], ...]
    fused_result_metadata: tuple[dict[str, Any], ...]
    identical_sequences: bool
    sequence_agreement: float | None
    top_k_recall: float | None
    full_energies: tuple[float | None, ...]
    fused_energies: tuple[float | None, ...]
    full_energy_kinds: tuple[EnergyKind, ...]
    fused_energy_kinds: tuple[EnergyKind, ...]
    energy_comparable: bool
    energy_comparison_reason: str | None
    full_candidate_pool_sha256: str | None
    fused_candidate_pool_sha256: str | None
    full_candidate_pool_size: int | None
    fused_candidate_pool_size: int | None
    candidate_pool_identical: bool | None
    result_availability_agreement: float | None
    finite_energy_differences: tuple[float, ...]
    maximum_energy_difference: float | None
    best_full_energy: float | None
    best_fused_energy: float | None
    best_energy_regret: float | None
    surrogate_routes: int
    full_model_routes: int
    initial_stage_parent_item_evaluations_bypassed: int
    mandatory_final_validation_parent_item_evaluations: int
    net_parent_item_evaluations_avoided: int
    # Backward-compatible alias for initial-stage bypasses only.
    parent_item_evaluations_avoided: int
    parent_item_evaluations_from_fallback: int
    routing_reasons: dict[str, int]
    target_objectives: int
    surrogate_seconds: float
    gate_seconds: float
    fallback_parent_seconds: float
    exact_parallel_routes: int
    initial_stage_parent_item_evaluations_parallelized: int
    exact_parallel_parent_seconds: float


@dataclass(frozen=True)
class PairedEvaluation:
    runs: tuple[PairedRun, ...]
    warmup: WarmupReport | None
    offline_surrogate_metrics: Mapping[str, Any] | None = None
    hardware: ExperimentHardware | None = None

    def as_dict(self) -> dict[str, Any]:
        run_records = [asdict(run) for run in self.runs]
        aggregate = aggregate_paired_runs(run_records, self.offline_surrogate_metrics)
        return {
            "schema_version": "2.0",
            "protocol": {
                "comparison": (
                    "same program, seed, ordered candidate pool when available, "
                    "stopping rule, and pinned hardware context"
                ),
                "measured_scope": "Program.run including routing, fallback, and final validation",
                "arm_order": "counterbalanced full/fused by seed position",
                "cold_start_in_primary_timing": False,
                "hardware_match_required": True,
                "hardware_match_level": "accelerator class and isolated Modal option set",
            },
            "hardware": self.hardware.as_dict() if self.hardware is not None else None,
            "startup": {
                "warmup": asdict(self.warmup) if self.warmup is not None else None,
                "cold_start_seconds": None,
                "note": (
                    "The unmeasured warmup duration is reported, but it is not a pure cold-start "
                    "measurement because it also contains normal program work."
                ),
            },
            "metrics": aggregate,
            "offline_surrogate_metrics": self.offline_surrogate_metrics,
            "runs": run_records,
            # Stable summary keys retained for existing consumers.
            "mean_speedup": aggregate["timing"]["mean_seed_speedup"],
            "all_final_sequences_identical": aggregate["accuracy"][
                "all_final_sequences_identical"
            ],
            "maximum_energy_difference": aggregate["accuracy"][
                "final_energy_max_absolute_difference"
            ],
        }


def evaluate_paired(
    build_program: Callable[[], Program],
    artifact: Any,
    *,
    seeds: Sequence[int],
    device: Literal["modal"] | None = None,
    modal_gpu: str | None = None,
    warmup: bool = True,
    warmup_seed: int | None = None,
    offline_surrogate_metrics: Mapping[str, Any] | None = None,
    on_progress: Callable[[PairedEvaluation], None] | None = None,
) -> PairedEvaluation:
    """Run the only timed experiment path; warmup never enters primary timing."""

    return evaluate_paired_transform(
        build_program,
        lambda program: transform_with_artifact(program, artifact),
        optimizer_index=int(artifact.manifest.optimizer_index),
        seeds=seeds,
        device=device,
        modal_gpu=modal_gpu,
        warmup=warmup,
        warmup_seed=warmup_seed,
        offline_surrogate_metrics=offline_surrogate_metrics,
        on_progress=on_progress,
    )


def evaluate_paired_transform(
    build_program: Callable[[], Program],
    transform_program: Callable[[Program], Program],
    *,
    optimizer_index: int,
    seeds: Sequence[int],
    device: Literal["modal"] | None = None,
    modal_gpu: str | None = None,
    warmup: bool = True,
    warmup_seed: int | None = None,
    offline_surrogate_metrics: Mapping[str, Any] | None = None,
    on_progress: Callable[[PairedEvaluation], None] | None = None,
) -> PairedEvaluation:
    """Evaluate any exact-matching FusionBundle with the canonical paired protocol."""

    resolved_seeds = tuple(seeds)
    if not resolved_seeds:
        raise ValueError("paired evaluation requires at least one seed")
    hardware = experiment_hardware(device, modal_gpu)

    warmup_report = None
    if warmup:
        resolved_warmup_seed = warmup_seed if warmup_seed is not None else max(resolved_seeds) + 1
        full = build_program()
        fused = transform_program(build_program())
        apply_program_seed(full, resolved_warmup_seed)
        apply_program_seed(fused, resolved_warmup_seed)
        warmup_order: tuple[Arm, Arm] = ("full", "fused")
        warmup_runs = _run_arms(
            full,
            fused,
            warmup_order,
            device,
            hardware,
            optimizer_index=optimizer_index,
        )
        warmup_report = WarmupReport(
            seed=resolved_warmup_seed,
            order=warmup_order,
            full_seconds=warmup_runs["full"].seconds,
            fused_seconds=warmup_runs["fused"].seconds,
            full_error_type=warmup_runs["full"].error_type,
            fused_error_type=warmup_runs["fused"].error_type,
        )

    runs: list[PairedRun] = []
    for index, seed in enumerate(resolved_seeds):
        runs.append(
            _paired_run(
                build_program,
                transform_program,
                optimizer_index=optimizer_index,
                seed=seed,
                order=("full", "fused") if index % 2 == 0 else ("fused", "full"),
                device=device,
                hardware=hardware,
            )
        )
        if on_progress is not None:
            on_progress(
                PairedEvaluation(
                    tuple(runs),
                    warmup_report,
                    offline_surrogate_metrics,
                    hardware,
                )
            )
    return PairedEvaluation(tuple(runs), warmup_report, offline_surrogate_metrics, hardware)


def apply_program_seed(program: Program, seed: int) -> None:
    """Set the program seed and the same derived optimizer seeds used by paired runs."""

    program.seed = seed
    for optimizer, derived in zip(
        program.optimizers,
        derive_seeds(seed, len(program.optimizers)),
        strict=True,
    ):
        optimizer.seed = derived


def _outputs(program: Program, *, optimizer_index: int) -> ProgramOutputs:
    results = tuple(
        sequence
        for construct in program.constructs
        for sequence in construct.joined_sequences
    )
    pool_relative = any(
        bool(getattr(optimizer, "pool_relative_objective", False))
        for optimizer in program.optimizers
    )
    optimizer = program.optimizers[optimizer_index]
    return ProgramOutputs(
        tuple(sequence.sequence for sequence in results),
        tuple(float(value) for value in program.energy_scores),
        result_metadata=tuple(sequence.metadata for sequence in results),
        energy_comparable=not pool_relative,
        energy_comparison_reason=(
            "The paper objective is normalized over the complete candidate pool; "
            "ProtoFuse final validation scores only retained candidates. Use top-k recall and "
            "raw per-objective metrics."
            if pool_relative
            else None
        ),
        candidate_pool_sha256=getattr(optimizer, "candidate_pool_sha256", None),
        candidate_pool_size=getattr(optimizer, "candidate_pool_size", None),
    )


def _execute(
    program: Program,
    device: Literal["modal"] | None,
    hardware: ExperimentHardware,
    *,
    optimizer_index: int,
) -> ArmExecution:
    started = perf_counter()
    try:
        with program_execution_scope(), pinned_modal_hardware(hardware):
            program.run(device=device)
    except Exception as error:  # noqa: BLE001 - experiment must retain failures by arm
        return ArmExecution(perf_counter() - started, None, type(error).__name__)
    return ArmExecution(
        perf_counter() - started,
        _outputs(program, optimizer_index=optimizer_index),
        None,
    )


def classify_proto_energy(value: float) -> EnergyKind:
    """Classify Proto's finite energy, skipped-NaN, and rejected/unfilled infinities."""

    if math.isnan(value):
        return "nan"
    if value == math.inf:
        return "positive_infinity"
    if value == -math.inf:
        return "negative_infinity"
    return "finite"


def _json_energies(values: tuple[float, ...]) -> tuple[float | None, ...]:
    return tuple(value if math.isfinite(value) else None for value in values)


def _agreement(left: Sequence[object], right: Sequence[object]) -> float | None:
    denominator = max(len(left), len(right))
    if denominator == 0:
        return None
    matches = sum(a == b for a, b in zip(left, right, strict=False))
    return matches / denominator


def _top_k_recall(full: tuple[str, ...], fused: tuple[str, ...]) -> float | None:
    expected = set(full)
    return len(expected & set(fused)) / len(expected) if expected else None


def _routing_metrics(program: Program) -> dict[str, Any]:
    routes = Counter[str]()
    reasons = Counter[str]()
    timings = Counter[str]()
    objective_count = 0
    avoided_parent_evaluations = 0
    fallback_parent_evaluations = 0
    exact_parallel_routes = 0
    parallelized_parent_evaluations = 0
    exact_parallel_seconds = 0.0
    exact_parent_fallback_seconds = 0.0
    for evaluator in getattr(program, "_protofuse_evaluators", ()):
        routes.update(evaluator.routing_counts)
        reasons.update(evaluator.routing_reasons)
        timings.update(evaluator.timing_seconds)
        group_objectives = len(evaluator.objectives)
        objective_count += group_objectives
        avoided_parent_evaluations += evaluator.routing_counts["surrogate"] * group_objectives
        fallback_parent_evaluations += evaluator.routing_counts["full_model"] * group_objectives
    for evaluator in getattr(program, "_protofuse_exact_evaluators", ()):
        reasons.update(evaluator.routing_reasons)
        group_objectives = len(evaluator.objectives)
        objective_count += group_objectives
        parallel_routes = int(evaluator.routing_counts["parallel"])
        parent_routes = int(evaluator.routing_counts["parent"])
        exact_parallel_routes += parallel_routes
        parallelized_parent_evaluations += parallel_routes * group_objectives
        fallback_parent_evaluations += parent_routes * group_objectives
        routes["full_model"] += parent_routes
        exact_parallel_seconds += float(evaluator.timing_seconds["parallel"])
        exact_parent_fallback_seconds += float(evaluator.timing_seconds["parent"])
    final_validation_parent_evaluations = sum(
        int(counter["parent_item_evaluations"])
        for counter in getattr(program, "_protofuse_validation_work", ())
    )
    return {
        "surrogate_routes": routes["surrogate"],
        "full_model_routes": routes["full_model"],
        "initial_stage_parent_item_evaluations_bypassed": avoided_parent_evaluations,
        "mandatory_final_validation_parent_item_evaluations": (
            final_validation_parent_evaluations
        ),
        "net_parent_item_evaluations_avoided": (
            avoided_parent_evaluations - final_validation_parent_evaluations
        ),
        # Retained for schema-2 consumers; this never included final validation.
        "parent_item_evaluations_avoided": avoided_parent_evaluations,
        "parent_item_evaluations_from_fallback": fallback_parent_evaluations,
        "routing_reasons": dict(sorted(reasons.items())),
        "target_objectives": objective_count,
        "surrogate_seconds": timings["surrogate"],
        "gate_seconds": timings["gate"],
        "fallback_parent_seconds": (
            float(timings["full_model"]) + exact_parent_fallback_seconds
        ),
        "exact_parallel_routes": exact_parallel_routes,
        "initial_stage_parent_item_evaluations_parallelized": (
            parallelized_parent_evaluations
        ),
        "exact_parallel_parent_seconds": exact_parallel_seconds,
    }


def _run_arms(
    full: Program,
    fused: Program,
    order: tuple[Arm, Arm],
    device: Literal["modal"] | None,
    hardware: ExperimentHardware,
    *,
    optimizer_index: int,
) -> dict[Arm, ArmExecution]:
    programs = {"full": full, "fused": fused}
    results: dict[Arm, ArmExecution] = {}
    for arm in order:
        results[arm] = _execute(
            programs[arm], device, hardware, optimizer_index=optimizer_index
        )
    return results


def _paired_run(
    build_program: Callable[[], Program],
    transform_program: Callable[[Program], Program],
    *,
    optimizer_index: int,
    seed: int,
    order: tuple[Arm, Arm],
    device: Literal["modal"] | None,
    hardware: ExperimentHardware,
) -> PairedRun:
    full = build_program()
    fused = transform_program(build_program())
    apply_program_seed(full, seed)
    apply_program_seed(fused, seed)
    executions = _run_arms(
        full,
        fused,
        order,
        device,
        hardware,
        optimizer_index=optimizer_index,
    )
    full_run = executions["full"]
    fused_run = executions["fused"]
    routing = _routing_metrics(fused)

    full_outputs = full_run.outputs or ProgramOutputs((), ())
    fused_outputs = fused_run.outputs or ProgramOutputs((), ())
    full_kinds = tuple(classify_proto_energy(value) for value in full_outputs.energies)
    fused_kinds = tuple(classify_proto_energy(value) for value in fused_outputs.energies)
    energy_comparable = full_outputs.energy_comparable and fused_outputs.energy_comparable
    energy_comparison_reason = (
        full_outputs.energy_comparison_reason or fused_outputs.energy_comparison_reason
    )
    candidate_pool_identical = (
        full_outputs.candidate_pool_sha256 == fused_outputs.candidate_pool_sha256
        and full_outputs.candidate_pool_size == fused_outputs.candidate_pool_size
        if full_outputs.candidate_pool_sha256 is not None
        and fused_outputs.candidate_pool_sha256 is not None
        and full_outputs.candidate_pool_size is not None
        and fused_outputs.candidate_pool_size is not None
        else None
    )
    candidate_pool_required = not energy_comparable
    differences = (
        tuple(
            abs(left - right)
            for left, right in zip(full_outputs.energies, fused_outputs.energies, strict=False)
            if math.isfinite(left) and math.isfinite(right)
        )
        if energy_comparable
        else ()
    )
    finite_full = tuple(value for value in full_outputs.energies if math.isfinite(value))
    finite_fused = tuple(value for value in fused_outputs.energies if math.isfinite(value))

    if full_run.error_type is not None or fused_run.error_type is not None:
        status: RunStatus = "arm_failed"
    elif candidate_pool_required and candidate_pool_identical is not True:
        status = "candidate_pool_mismatch"
    elif len(full_outputs.energies) != len(fused_outputs.energies):
        status = "output_length_mismatch"
    elif any(kind != "finite" for kind in (*full_kinds, *fused_kinds)):
        # Proto uses NaN for skipped evaluations and +inf for rejected/unfilled results.
        status = "non_finite_energy"
    else:
        status = "ok"

    speedup = None
    if (
        full_run.error_type is None
        and fused_run.error_type is None
        and (not candidate_pool_required or candidate_pool_identical is True)
        and fused_run.seconds > 0
    ):
        speedup = full_run.seconds / fused_run.seconds
    best_full = min(finite_full, default=None) if energy_comparable else None
    best_fused = min(finite_fused, default=None) if energy_comparable else None
    regret = best_fused - best_full if best_full is not None and best_fused is not None else None
    availability_full = tuple(kind == "finite" for kind in full_kinds)
    availability_fused = tuple(kind == "finite" for kind in fused_kinds)

    return PairedRun(
        seed=seed,
        order=order,
        status=status,
        full_seconds=full_run.seconds,
        fused_seconds=fused_run.seconds,
        speedup=speedup,
        full_error_type=full_run.error_type,
        fused_error_type=fused_run.error_type,
        full_sequences=full_outputs.sequences,
        fused_sequences=fused_outputs.sequences,
        full_result_metadata=full_outputs.result_metadata,
        fused_result_metadata=fused_outputs.result_metadata,
        identical_sequences=full_outputs.sequences == fused_outputs.sequences,
        sequence_agreement=_agreement(full_outputs.sequences, fused_outputs.sequences),
        top_k_recall=_top_k_recall(full_outputs.sequences, fused_outputs.sequences),
        full_energies=_json_energies(full_outputs.energies),
        fused_energies=_json_energies(fused_outputs.energies),
        full_energy_kinds=full_kinds,
        fused_energy_kinds=fused_kinds,
        energy_comparable=energy_comparable,
        energy_comparison_reason=energy_comparison_reason,
        full_candidate_pool_sha256=full_outputs.candidate_pool_sha256,
        fused_candidate_pool_sha256=fused_outputs.candidate_pool_sha256,
        full_candidate_pool_size=full_outputs.candidate_pool_size,
        fused_candidate_pool_size=fused_outputs.candidate_pool_size,
        candidate_pool_identical=candidate_pool_identical,
        result_availability_agreement=_agreement(availability_full, availability_fused),
        finite_energy_differences=differences,
        maximum_energy_difference=max(differences, default=None),
        best_full_energy=best_full,
        best_fused_energy=best_fused,
        best_energy_regret=regret,
        **routing,
    )
