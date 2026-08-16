"""Development-only residual learning for the frozen CUSTOM sampled-MFE path.

This module does not package or approve a persistent runtime artifact.  It tests whether a
position-sensitive model can predict the error left by the already frozen stride-8 estimator and
can build an unreviewed, in-memory bundle for controlled replay.  Model choice uses only the
declared development split; an external cohort may be evaluated only after one candidate and all
of its routing thresholds have been frozen.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import pickle
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import numpy as np
import sklearn  # type: ignore[import-untyped]
from proto_language.core import ConstraintOutput, Program
from proto_language.core import Sequence as ProtoSequence
from sklearn.ensemble import ExtraTreesRegressor  # type: ignore[import-untyped]
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from protofuse.phillip.custom_constraints import CustomMetricConfig, _outputs
from protofuse.sai.artifacts import file_sha256
from protofuse.sai.exact_custom import (
    FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
    FROZEN_CUSTOM_MFE_SLOPE,
    FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL,
    FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
)
from protofuse.sai.training import _rank_correlations, _read_trace

FEATURE_SPEC_VERSION = "custom-mfe-residual-v1"
EXPECTED_SEQUENCE_LENGTH = 717
EXPECTED_WINDOWS = 80
POSITION_BINS = 24
RIDGE_ALPHA_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
RIDGE_ENSEMBLE_SIZE = 8
EXTRA_TREES_COUNT = 128
MODEL_RANDOM_SEED = 20260816


@dataclass(frozen=True)
class ResidualGates:
    """Predeclared scientific and value-add gates for residual learning."""

    max_normalized_mae: float = 0.05
    min_spearman: float = 0.90
    min_coverage: float = 0.30
    min_relative_mae_improvement: float = 0.10
    max_spearman_degradation: float = 0.002
    calibration_quantile: float = 0.99

    def as_dict(self) -> dict[str, float]:
        return {
            "max_normalized_mae": self.max_normalized_mae,
            "min_spearman": self.min_spearman,
            "min_coverage": self.min_coverage,
            "min_relative_mae_improvement": self.min_relative_mae_improvement,
            "max_spearman_degradation": self.max_spearman_degradation,
            "calibration_quantile": self.calibration_quantile,
        }


DEFAULT_RESIDUAL_GATES = ResidualGates()


@dataclass(frozen=True)
class TraceExample:
    """One exact parent observation from one independent pool group."""

    group_id: str
    input_sha256: str
    sequence: str
    actual_mfe_kcal_mol: float


@dataclass(frozen=True)
class ResidualDataset:
    """Feature-complete examples with the frozen sampled baseline beside the parent."""

    groups: np.ndarray
    input_hashes: np.ndarray
    actual: np.ndarray
    baseline: np.ndarray
    baseline_uncertainty: np.ndarray
    features: np.ndarray
    trace_sha256: tuple[str, ...]


@dataclass
class FittedResidualCandidate:
    """One in-memory candidate frozen before external evaluation."""

    family: Literal["ridge", "extra_trees"]
    config: dict[str, Any]
    scaler: StandardScaler
    model: Any
    support_center: np.ndarray
    support_scale: np.ndarray
    support_threshold: float
    uncertainty_threshold: float
    model_sha256: str

    def member_predictions(self, features: np.ndarray) -> np.ndarray:
        transformed = self.scaler.transform(features)
        if self.family == "ridge":
            return np.stack([member.predict(transformed) for member in self.model])
        return np.stack([tree.predict(transformed) for tree in self.model.estimators_])


@dataclass(frozen=True)
class ResidualFeatureChunk:
    """One ordered runtime batch for process-parallel feature extraction."""

    index: int
    sequences: tuple[str, ...]


@dataclass(frozen=True)
class ResidualFeatureChunkResult:
    """Position-sensitive features returned in the input sequence order."""

    index: int
    features: np.ndarray
    baselines: tuple[float, ...]
    baseline_uncertainties: tuple[float, ...]


def load_custom_mfe_examples(
    trace_paths: Sequence[Path],
    *,
    allowed_groups: set[str],
    expected_rows_per_group: int = 1000,
) -> tuple[tuple[TraceExample, ...], tuple[str, ...]]:
    """Load exact full-tier CUSTOM MFE rows with strict group and trace checks."""

    if not trace_paths:
        raise ValueError("CUSTOM residual experiment requires at least one trace")
    examples: list[TraceExample] = []
    trace_hashes: list[str] = []
    observed_groups: set[str] = set()
    for unresolved_path in trace_paths:
        path = unresolved_path.resolve()
        digest = file_sha256(path)
        if digest in trace_hashes:
            raise ValueError("CUSTOM residual experiment received duplicate trace content")
        trace_hashes.append(digest)
        rows = [
            row
            for row in _read_trace(path)
            if row.optimizer_index == 0 and row.constraint_label == "custom_mfe"
        ]
        if len(rows) != expected_rows_per_group:
            raise ValueError(
                f"{path} has {len(rows)} CUSTOM MFE rows; expected {expected_rows_per_group}"
            )
        groups = {row.group_id for row in rows}
        if len(groups) != 1:
            raise ValueError(f"{path} must contain exactly one group")
        group_id = next(iter(groups))
        if group_id not in allowed_groups:
            raise ValueError(f"trace group {group_id!r} is outside the declared cohort")
        if group_id in observed_groups:
            raise ValueError(f"trace group {group_id!r} appears more than once")
        observed_groups.add(group_id)
        proposal_indexes = {row.proposal_index for row in rows}
        if proposal_indexes != set(range(expected_rows_per_group)):
            raise ValueError(f"trace group {group_id!r} has incomplete proposal indexes")
        for row in rows:
            raw = row.metadata.get("mfe_kcal_mol") if isinstance(row.metadata, dict) else None
            if (
                row.error is not None
                or row.input_sequences is None
                or len(row.input_sequences) != 1
                or row.tier != "full"
                or isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(float(raw))
                or len(row.input_sha256) != 1
            ):
                raise ValueError(f"{path} contains an incompatible CUSTOM MFE row")
            sequence = row.input_sequences[0]
            if len(sequence) != EXPECTED_SEQUENCE_LENGTH:
                raise ValueError(
                    f"CUSTOM residual sequence has length {len(sequence)}; "
                    f"expected {EXPECTED_SEQUENCE_LENGTH}"
                )
            examples.append(
                TraceExample(
                    group_id=group_id,
                    input_sha256=row.input_sha256[0],
                    sequence=sequence,
                    actual_mfe_kcal_mol=float(raw),
                )
            )
    missing = sorted(allowed_groups - observed_groups)
    if missing:
        raise ValueError(f"declared cohort is missing trace groups: {missing}")
    return tuple(examples), tuple(trace_hashes)


def residual_feature_names() -> tuple[str, ...]:
    """Return the stable ordered feature schema."""

    names = [f"window_mfe_{index:03d}" for index in range(EXPECTED_WINDOWS)]
    names.extend(f"window_delta_{index:03d}" for index in range(EXPECTED_WINDOWS - 1))
    names.extend(
        (
            "window_mean",
            "window_std",
            "window_min",
            "window_max",
            "window_q10",
            "window_q25",
            "window_q50",
            "window_q75",
            "window_q90",
            "window_mean_abs_delta",
            "window_first_member_mean",
            "window_second_member_mean",
        )
    )
    for kmer_length in (1, 2, 3):
        names.extend(
            "kmer_" + "".join(kmer)
            for kmer in itertools.product("ACGT", repeat=kmer_length)
        )
    names.extend(
        f"position_bin_{bin_index:02d}_{base}"
        for bin_index in range(POSITION_BINS)
        for base in "ACGT"
    )
    return tuple(names)


def custom_mfe_residual_features(sequence: str) -> tuple[np.ndarray, float, float]:
    """Compute position-sensitive features and the frozen sampled prediction."""

    if len(sequence) != EXPECTED_SEQUENCE_LENGTH or set(sequence) - set("ACGT"):
        raise ValueError("CUSTOM residual features require one 717-base canonical DNA sequence")
    import RNA  # type: ignore[import-untyped]

    window_values = np.asarray(
        [
            float(RNA.fold(sequence[start : start + 40])[1])
            for start in range(
                40,
                len(sequence) - 39,
                FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
            )
        ],
        dtype=np.float64,
    )
    if len(window_values) != EXPECTED_WINDOWS or not np.all(np.isfinite(window_values)):
        raise ValueError("CUSTOM residual feature extraction returned invalid window energies")
    sampled_mean = float(window_values.mean())
    first_mean = float(window_values[::2].mean())
    second_mean = float(window_values[1::2].mean())
    baseline = (
        FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL
        + FROZEN_CUSTOM_MFE_SLOPE * sampled_mean
    )
    uncertainty = (
        abs(FROZEN_CUSTOM_MFE_SLOPE * (first_mean - second_mean)) / 2.0
    )
    quantiles = np.quantile(window_values, (0.10, 0.25, 0.50, 0.75, 0.90))
    deltas = np.diff(window_values)
    summary = np.asarray(
        [
            sampled_mean,
            float(window_values.std()),
            float(window_values.min()),
            float(window_values.max()),
            *quantiles.tolist(),
            float(np.abs(deltas).mean()),
            first_mean,
            second_mean,
        ],
        dtype=np.float64,
    )
    kmer_features: list[float] = []
    for kmer_length in (1, 2, 3):
        counts = Counter(
            sequence[index : index + kmer_length]
            for index in range(len(sequence) - kmer_length + 1)
        )
        denominator = len(sequence) - kmer_length + 1
        kmer_features.extend(
            counts.get("".join(kmer), 0) / denominator
            for kmer in itertools.product("ACGT", repeat=kmer_length)
        )
    positional_features: list[float] = []
    for chunk in np.array_split(np.frombuffer(sequence.encode("ascii"), dtype="S1"), POSITION_BINS):
        positional_features.extend(float(np.mean(chunk == base.encode())) for base in "ACGT")
    features = np.concatenate(
        (
            window_values,
            deltas,
            summary,
            np.asarray(kmer_features, dtype=np.float64),
            np.asarray(positional_features, dtype=np.float64),
        )
    )
    if len(features) != len(residual_feature_names()) or not np.all(np.isfinite(features)):
        raise RuntimeError("CUSTOM residual feature schema drifted")
    return features, baseline, uncertainty


def _feature_chunk(
    examples: tuple[TraceExample, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = [custom_mfe_residual_features(example.sequence) for example in examples]
    return (
        np.stack([row[0] for row in rows]),
        np.asarray([row[1] for row in rows], dtype=np.float64),
        np.asarray([row[2] for row in rows], dtype=np.float64),
    )


def residual_feature_worker(chunk: ResidualFeatureChunk) -> ResidualFeatureChunkResult:
    """Extract runtime features without shipping a learned model to worker processes."""

    rows = [custom_mfe_residual_features(sequence) for sequence in chunk.sequences]
    return ResidualFeatureChunkResult(
        index=chunk.index,
        features=np.stack([row[0] for row in rows]).astype(np.float32),
        baselines=tuple(row[1] for row in rows),
        baseline_uncertainties=tuple(row[2] for row in rows),
    )


def build_residual_dataset(
    examples: tuple[TraceExample, ...],
    *,
    trace_sha256: tuple[str, ...],
    workers: int = 8,
    chunk_size: int = 100,
    on_progress: Callable[[int, int], None] | None = None,
) -> ResidualDataset:
    """Compute features in ordered process chunks without evaluating the exact parent."""

    if workers < 1 or chunk_size < 1:
        raise ValueError("workers and chunk_size must be positive")
    chunks = tuple(
        examples[start : start + chunk_size]
        for start in range(0, len(examples), chunk_size)
    )
    resolved_workers = min(workers, len(chunks))
    matrices: list[np.ndarray] = []
    baselines: list[np.ndarray] = []
    uncertainties: list[np.ndarray] = []
    with ProcessPoolExecutor(
        max_workers=resolved_workers,
        mp_context=get_context("spawn"),
    ) as executor:
        completed = 0
        for matrix, baseline, uncertainty in executor.map(_feature_chunk, chunks):
            matrices.append(matrix)
            baselines.append(baseline)
            uncertainties.append(uncertainty)
            completed += len(matrix)
            if on_progress is not None:
                on_progress(completed, len(examples))
    return ResidualDataset(
        groups=np.asarray([example.group_id for example in examples]),
        input_hashes=np.asarray([example.input_sha256 for example in examples]),
        actual=np.asarray(
            [example.actual_mfe_kcal_mol for example in examples], dtype=np.float64
        ),
        baseline=np.concatenate(baselines),
        baseline_uncertainty=np.concatenate(uncertainties),
        features=np.concatenate(matrices).astype(np.float32),
        trace_sha256=trace_sha256,
    )


def dataset_fingerprint(trace_sha256: Sequence[str]) -> str:
    payload = "\n".join((FEATURE_SPEC_VERSION, *trace_sha256)).encode()
    return hashlib.sha256(payload).hexdigest()


def save_residual_dataset(path: Path, dataset: ResidualDataset) -> None:
    """Persist an ignored numeric cache with no raw sequences."""

    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        schema_version=np.asarray(FEATURE_SPEC_VERSION),
        fingerprint=np.asarray(dataset_fingerprint(dataset.trace_sha256)),
        groups=dataset.groups,
        input_hashes=dataset.input_hashes,
        actual=dataset.actual,
        baseline=dataset.baseline,
        baseline_uncertainty=dataset.baseline_uncertainty,
        features=dataset.features,
        trace_sha256=np.asarray(dataset.trace_sha256),
    )


def load_residual_dataset(
    path: Path,
    *,
    expected_trace_sha256: tuple[str, ...],
) -> ResidualDataset:
    """Load a cache only when its trace hashes and feature schema match exactly."""

    with np.load(path, allow_pickle=False) as values:
        if str(values["schema_version"]) != FEATURE_SPEC_VERSION:
            raise ValueError("CUSTOM residual cache uses a different feature schema")
        expected = dataset_fingerprint(expected_trace_sha256)
        if str(values["fingerprint"]) != expected:
            raise ValueError("CUSTOM residual cache does not match the declared traces")
        return ResidualDataset(
            groups=values["groups"],
            input_hashes=values["input_hashes"],
            actual=values["actual"],
            baseline=values["baseline"],
            baseline_uncertainty=values["baseline_uncertainty"],
            features=values["features"],
            trace_sha256=tuple(str(value) for value in values["trace_sha256"]),
        )


def _quantile(values: np.ndarray, probability: float) -> float:
    return float(np.quantile(values, probability, method="higher"))


def _group_bootstrap_indices(
    groups: np.ndarray,
    train_groups: tuple[str, ...],
    rng: np.random.Generator,
) -> np.ndarray:
    sampled = rng.choice(train_groups, size=len(train_groups), replace=True)
    return np.concatenate([np.flatnonzero(groups == group) for group in sampled])


def _support_scores(
    features: np.ndarray,
    center: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    return np.sqrt(np.mean(np.square((features - center) / scale), axis=1))


def _model_hash(*parts: Any) -> str:
    return hashlib.sha256(pickle.dumps(parts, protocol=5)).hexdigest()


def fit_residual_candidates(
    dataset: ResidualDataset,
    *,
    train_groups: tuple[str, ...],
    calibration_groups: tuple[str, ...],
    gates: ResidualGates = DEFAULT_RESIDUAL_GATES,
) -> tuple[FittedResidualCandidate, FittedResidualCandidate]:
    """Fit the two predeclared families and freeze calibration-only route thresholds."""

    train_mask = np.isin(dataset.groups, train_groups)
    calibration_mask = np.isin(dataset.groups, calibration_groups)
    if not train_mask.any() or not calibration_mask.any():
        raise ValueError("CUSTOM residual fit requires non-empty train and calibration groups")
    if np.any(train_mask & calibration_mask):
        raise ValueError("CUSTOM residual train and calibration groups overlap")
    target = dataset.actual - dataset.baseline
    scaler = StandardScaler().fit(dataset.features[train_mask])
    transformed = scaler.transform(dataset.features)
    alpha_scores: list[tuple[float, float]] = []
    for alpha in RIDGE_ALPHA_GRID:
        trial = Ridge(alpha=alpha, solver="lsqr").fit(
            transformed[train_mask], target[train_mask]
        )
        error = float(
            np.abs(
                target[calibration_mask] - trial.predict(transformed[calibration_mask])
            ).mean()
        )
        alpha_scores.append((error, alpha))
    selected_alpha = min(alpha_scores)[1]
    rng = np.random.default_rng(MODEL_RANDOM_SEED)
    ridge_members: list[Ridge] = []
    for _ in range(RIDGE_ENSEMBLE_SIZE):
        indexes = _group_bootstrap_indices(dataset.groups, train_groups, rng)
        ridge_members.append(
            Ridge(alpha=selected_alpha, solver="lsqr").fit(
                transformed[indexes], target[indexes]
            )
        )

    tree_model = ExtraTreesRegressor(
        n_estimators=EXTRA_TREES_COUNT,
        min_samples_leaf=2,
        max_features=0.75,
        bootstrap=True,
        n_jobs=-1,
        random_state=MODEL_RANDOM_SEED,
    ).fit(transformed[train_mask], target[train_mask])

    center = dataset.features[train_mask].mean(axis=0, dtype=np.float64)
    scale = np.maximum(dataset.features[train_mask].std(axis=0), 1e-6)
    support = _support_scores(dataset.features, center, scale)
    support_threshold = _quantile(
        support[calibration_mask], gates.calibration_quantile
    )

    candidates: list[FittedResidualCandidate] = []
    for family, model, config in (
        (
            "ridge",
            ridge_members,
            {
                "estimator": "group-bootstrap Ridge residual ensemble",
                "alpha_grid": list(RIDGE_ALPHA_GRID),
                "selected_alpha_by_calibration_mae": selected_alpha,
                "ensemble_size": RIDGE_ENSEMBLE_SIZE,
                "solver": "lsqr",
            },
        ),
        (
            "extra_trees",
            tree_model,
            {
                "estimator": "ExtraTreesRegressor residual ensemble",
                "tree_count": EXTRA_TREES_COUNT,
                "min_samples_leaf": 2,
                "max_features": 0.75,
                "bootstrap": True,
            },
        ),
    ):
        candidate = FittedResidualCandidate(
            family=family,  # type: ignore[arg-type]
            config=config,
            scaler=scaler,
            model=model,
            support_center=center,
            support_scale=scale,
            support_threshold=support_threshold,
            uncertainty_threshold=math.nan,
            model_sha256=_model_hash(family, scaler, model, config),
        )
        member_predictions = candidate.member_predictions(dataset.features)
        uncertainty = member_predictions.std(axis=0)
        candidate.uncertainty_threshold = _quantile(
            uncertainty[calibration_mask], gates.calibration_quantile
        )
        candidates.append(candidate)
    return candidates[0], candidates[1]


class ResidualCustomMfeEvaluator:
    """Frozen sampled-MFE residual predictor with exact per-item fallback."""

    def __init__(
        self,
        parent_function: Callable[
            [list[tuple[ProtoSequence, ...]], CustomMetricConfig],
            list[ConstraintOutput],
        ],
        parent_config: CustomMetricConfig,
        workers: int,
        candidate: FittedResidualCandidate,
    ) -> None:
        if workers < 1:
            raise ValueError("residual CUSTOM MFE workers must be positive")
        self.parent_function = parent_function
        self.parent_config = parent_config
        self.workers = min(workers, 8)
        self.candidate = candidate
        self.objectives = ("custom_mfe",)
        self.routing_counts = {"surrogate": 0, "full_model": 0}
        self.routing_reasons: Counter[str] = Counter()
        self.batch_counts = {"surrogate": 0, "full_model": 0, "parallel_failures": 0}
        self.timing_seconds = {"surrogate": 0.0, "gate": 0.0, "full_model": 0.0}
        self.last_parallel_error_type: str | None = None

    def __call__(
        self,
        input_sequences: list[tuple[ProtoSequence, ...]],
        config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        return self.evaluate(input_sequences, config)

    def evaluate(
        self,
        input_sequences: list[tuple[ProtoSequence, ...]],
        config: CustomMetricConfig,
    ) -> list[ConstraintOutput]:
        del config
        if not input_sequences:
            return []
        started = perf_counter()
        try:
            (
                values,
                baseline_uncertainties,
                model_uncertainties,
                support_scores,
            ) = self._parallel_predictions(input_sequences)
            outputs = _outputs(
                values,
                metric="mfe_kcal_mol",
                lower=-200.0,
                upper=0.0,
                maximize=False,
            )
        except Exception as error:  # noqa: BLE001 - exact fallback is mandatory
            self.timing_seconds["surrogate"] += perf_counter() - started
            self.batch_counts["parallel_failures"] += 1
            self.last_parallel_error_type = type(error).__name__
            reason = f"residual_mfe_error:{type(error).__name__}"
            self.routing_reasons[reason] += len(input_sequences)
            return self._fallback_all(input_sequences, reason=reason)

        self.timing_seconds["surrogate"] += perf_counter() - started
        self.batch_counts["surrogate"] += 1
        self.last_parallel_error_type = None
        gate_started = perf_counter()
        rejection_reasons: dict[int, str] = {}
        try:
            for index, value in enumerate(values):
                if not math.isfinite(value) or not -200.0 <= value <= 0.0:
                    rejection_reasons[index] = "residual_mfe_invalid_prediction"
                elif (
                    not math.isfinite(baseline_uncertainties[index])
                    or baseline_uncertainties[index]
                    > FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
                ):
                    rejection_reasons[index] = "residual_mfe_baseline_uncertain"
                elif (
                    not math.isfinite(support_scores[index])
                    or support_scores[index] > self.candidate.support_threshold
                ):
                    rejection_reasons[index] = "residual_mfe_out_of_domain"
                elif (
                    not math.isfinite(model_uncertainties[index])
                    or model_uncertainties[index]
                    > self.candidate.uncertainty_threshold
                ):
                    rejection_reasons[index] = "residual_mfe_model_uncertain"
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
        self.routing_reasons["frozen_sampled_window_ridge_residual"] += accepted_count
        routed: list[ConstraintOutput] = []
        for index, output in enumerate(outputs):
            diagnostic = {
                "protofuse_residual_model_sha256": self.candidate.model_sha256,
                "protofuse_sampled_uncertainty_kcal_mol": baseline_uncertainties[index],
                "protofuse_residual_uncertainty_kcal_mol": model_uncertainties[index],
                "protofuse_residual_support_score": support_scores[index],
            }
            if index in fallback_by_index:
                routed.append(
                    fallback_by_index[index].model_copy(
                        update={
                            "metadata": {
                                **fallback_by_index[index].metadata,
                                **diagnostic,
                                "protofuse_route": "full_model",
                                "protofuse_reason": rejection_reasons[index],
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
                                **diagnostic,
                                "protofuse_route": "surrogate",
                                "protofuse_reason": (
                                    "frozen_sampled_window_ridge_residual"
                                ),
                                "protofuse_window_stride": (
                                    FROZEN_CUSTOM_MFE_WINDOW_STRIDE
                                ),
                            }
                        }
                    )
                )
        return routed

    def _parallel_predictions(
        self,
        input_sequences: list[tuple[ProtoSequence, ...]],
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        sequences = [sequence.sequence for (sequence,) in input_sequences]
        worker_count = min(self.workers, len(sequences))
        chunk_size = math.ceil(len(sequences) / worker_count)
        chunks = tuple(
            ResidualFeatureChunk(
                index=index,
                sequences=tuple(sequences[start : start + chunk_size]),
            )
            for index, start in enumerate(range(0, len(sequences), chunk_size))
        )
        with ProcessPoolExecutor(
            max_workers=worker_count,
            mp_context=get_context("spawn"),
        ) as executor:
            results = sorted(
                executor.map(residual_feature_worker, chunks),
                key=lambda result: result.index,
            )
        features = np.concatenate([result.features for result in results])
        baselines = np.concatenate(
            [np.asarray(result.baselines, dtype=np.float64) for result in results]
        )
        baseline_uncertainties = np.concatenate(
            [
                np.asarray(result.baseline_uncertainties, dtype=np.float64)
                for result in results
            ]
        )
        member_residuals = self.candidate.member_predictions(features)
        predicted = baselines + member_residuals.mean(axis=0)
        model_uncertainties = member_residuals.std(axis=0)
        support_scores = _support_scores(
            features,
            self.candidate.support_center,
            self.candidate.support_scale,
        )
        if not (
            len(predicted)
            == len(baseline_uncertainties)
            == len(model_uncertainties)
            == len(support_scores)
            == len(input_sequences)
        ):
            raise ValueError("residual CUSTOM MFE returned incomplete predictions")
        return (
            predicted.tolist(),
            baseline_uncertainties.tolist(),
            model_uncertainties.tolist(),
            support_scores.tolist(),
        )

    def _parent_outputs(
        self,
        input_sequences: list[tuple[ProtoSequence, ...]],
    ) -> list[ConstraintOutput]:
        started = perf_counter()
        try:
            outputs = list(self.parent_function(input_sequences, self.parent_config))
            if len(outputs) != len(input_sequences):
                raise ValueError(
                    f"CUSTOM MFE parent returned {len(outputs)} outputs for "
                    f"{len(input_sequences)} inputs"
                )
            return outputs
        finally:
            self.timing_seconds["full_model"] += perf_counter() - started

    def _fallback_all(
        self,
        input_sequences: list[tuple[ProtoSequence, ...]],
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


def build_residual_custom_mfe_bundle(
    reference_program: Program,
    *,
    candidate: FittedResidualCandidate,
    workers: int = 8,
) -> Any:
    """Build an unreviewed experiment-only bundle for paired residual replay."""

    from protofuse.sai.registry import FusionBundle
    from protofuse.sai.signatures import step_group_signature
    from protofuse.sai.transform import _transform_custom_mfe_executor

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
            evaluator_factory=lambda function, config: ResidualCustomMfeEvaluator(
                function,
                config,
                workers,
                candidate,
            ),
            sampled=True,
        )

    return FusionBundle(
        fusion_id="custom-mfe-sampled-ridge-residual",
        version=f"{FEATURE_SPEC_VERSION}-{candidate.model_sha256[:12]}",
        matches=matches,
        apply=apply,
    )


def evaluate_residual_candidate(
    candidate: FittedResidualCandidate,
    dataset: ResidualDataset,
    *,
    groups: tuple[str, ...],
    gates: ResidualGates = DEFAULT_RESIDUAL_GATES,
) -> dict[str, Any]:
    """Evaluate a frozen candidate and compare it with baseline on the same accepted rows."""

    cohort = np.isin(dataset.groups, groups)
    if not cohort.any():
        raise ValueError("CUSTOM residual evaluation cohort is empty")
    member_residuals = candidate.member_predictions(dataset.features)
    residual = member_residuals.mean(axis=0)
    uncertainty = member_residuals.std(axis=0)
    support = _support_scores(
        dataset.features,
        candidate.support_center,
        candidate.support_scale,
    )
    predicted = dataset.baseline + residual
    accepted = (
        cohort
        & np.isfinite(predicted)
        & np.isfinite(uncertainty)
        & (dataset.baseline_uncertainty
           <= FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL)
        & (support <= candidate.support_threshold)
        & (uncertainty <= candidate.uncertainty_threshold)
    )
    cohort_count = int(cohort.sum())
    accepted_count = int(accepted.sum())
    coverage = accepted_count / cohort_count
    if not accepted_count:
        metrics: dict[str, float | None] = {
            "q05_kcal_mol": None,
            "q95_kcal_mol": None,
            "q95_q05_kcal_mol": None,
            "residual_mae_kcal_mol": None,
            "residual_normalized_mae": None,
            "residual_spearman": None,
            "baseline_mae_kcal_mol_same_rows": None,
            "baseline_normalized_mae_same_rows": None,
            "baseline_spearman_same_rows": None,
            "relative_mae_improvement": None,
            "spearman_delta": None,
        }
    else:
        actual = dataset.actual[accepted]
        residual_prediction = predicted[accepted]
        baseline_prediction = dataset.baseline[accepted]
        q05, q95 = np.quantile(actual, (0.05, 0.95))
        span = float(q95 - q05)
        residual_mae = float(np.abs(actual - residual_prediction).mean())
        baseline_mae = float(np.abs(actual - baseline_prediction).mean())
        residual_spearman = _rank_correlations(
            actual[:, None], residual_prediction[:, None]
        )[0]
        baseline_spearman = _rank_correlations(
            actual[:, None], baseline_prediction[:, None]
        )[0]
        spearman_delta = (
            residual_spearman - baseline_spearman
            if residual_spearman is not None and baseline_spearman is not None
            else None
        )
        metrics = {
            "q05_kcal_mol": float(q05),
            "q95_kcal_mol": float(q95),
            "q95_q05_kcal_mol": span,
            "residual_mae_kcal_mol": residual_mae,
            "residual_normalized_mae": residual_mae / span if span > 0.0 else None,
            "residual_spearman": residual_spearman,
            "baseline_mae_kcal_mol_same_rows": baseline_mae,
            "baseline_normalized_mae_same_rows": (
                baseline_mae / span if span > 0.0 else None
            ),
            "baseline_spearman_same_rows": baseline_spearman,
            "relative_mae_improvement": (
                (baseline_mae - residual_mae) / baseline_mae
                if baseline_mae > 0.0
                else None
            ),
            "spearman_delta": spearman_delta,
        }
    checks = {
        "accepted_samples": accepted_count > 0,
        "normalized_mae": (
            metrics["residual_normalized_mae"] is not None
            and metrics["residual_normalized_mae"] <= gates.max_normalized_mae
        ),
        "spearman": (
            metrics["residual_spearman"] is not None
            and metrics["residual_spearman"] >= gates.min_spearman
        ),
        "coverage": accepted_count > 0 and coverage >= gates.min_coverage,
        "relative_mae_improvement": (
            metrics["relative_mae_improvement"] is not None
            and metrics["relative_mae_improvement"]
            >= gates.min_relative_mae_improvement
        ),
        "rank_non_degradation": (
            metrics["spearman_delta"] is not None
            and metrics["spearman_delta"] >= -gates.max_spearman_degradation
        ),
    }
    routing: Counter[str] = Counter()
    routing["accepted_residual"] = accepted_count
    routing["baseline_uncertain"] = int(
        np.sum(
            cohort
            & (
                dataset.baseline_uncertainty
                > FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
            )
        )
    )
    routing["support_ood"] = int(
        np.sum(
            cohort
            & (
                dataset.baseline_uncertainty
                <= FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
            )
            & (support > candidate.support_threshold)
        )
    )
    routing["model_uncertain"] = cohort_count - sum(routing.values())
    return {
        "family": candidate.family,
        "model_sha256": candidate.model_sha256,
        "status": "pass" if all(checks.values()) else "fail",
        "passed": all(checks.values()),
        "groups": list(groups),
        "samples": {
            "total": cohort_count,
            "accepted": accepted_count,
            "coverage": coverage,
            "routing": dict(routing),
        },
        "metrics": metrics,
        "thresholds": {
            **gates.as_dict(),
            "baseline_uncertainty_kcal_mol": (
                FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
            ),
            "support_score": candidate.support_threshold,
            "model_uncertainty_kcal_mol": candidate.uncertainty_threshold,
        },
        "checks": checks,
    }


def select_development_candidate(
    candidates: Sequence[FittedResidualCandidate],
    reports: Sequence[dict[str, Any]],
) -> FittedResidualCandidate | None:
    """Apply the frozen winner rule: pass every gate, then maximize MAE improvement."""

    if len(candidates) != len(reports):
        raise ValueError("candidate and report counts differ")
    eligible = [
        (candidate, report)
        for candidate, report in zip(candidates, reports, strict=True)
        if report["passed"]
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (
            item[1]["metrics"]["relative_mae_improvement"],
            item[1]["metrics"]["residual_spearman"],
            item[1]["samples"]["coverage"],
        ),
    )[0]


def experiment_metadata() -> dict[str, Any]:
    """Return the frozen, reportable method declaration."""

    return {
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "feature_count": len(residual_feature_names()),
        "feature_families": [
            "80 ordered stride-8 RNAfold window energies",
            "79 adjacent energy deltas and 12 curve summaries",
            "canonical 1/2/3-mer frequencies",
            f"per-base frequencies in {POSITION_BINS} ordered sequence bins",
        ],
        "target": "exact body MFE minus frozen stride-8 affine prediction",
        "candidate_families": ["group-bootstrap ridge", "Extra Trees"],
        "winner_rule": (
            "pass every absolute and value-add gate, then maximize relative MAE "
            "improvement, Spearman, and coverage in that order"
        ),
        "random_seed": MODEL_RANDOM_SEED,
        "libraries": {"numpy": np.__version__, "scikit_learn": sklearn.__version__},
    }
