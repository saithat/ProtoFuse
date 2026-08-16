"""One offline, same-split comparison of compact multi-output surrogate families."""

from __future__ import annotations

import pickle
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import numpy as np
import sklearn  # type: ignore[import-untyped]
from sklearn.ensemble import ExtraTreesRegressor  # type: ignore[import-untyped]
from sklearn.exceptions import ConvergenceWarning  # type: ignore[import-untyped]
from sklearn.neural_network import MLPRegressor  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from protofuse.sai.model import OutputNormalization, SequenceFeatureSchema
from protofuse.sai.training import (
    PreparedTrainingData,
    TeacherSample,
    _normalized_mae,
    _q95_q05_ranges,
    _quantile,
    _rank_correlations,
    prepare_training_data,
)


@dataclass(frozen=True)
class _FittedFamily:
    config: dict[str, Any]
    predict_members: Callable[[np.ndarray], np.ndarray]
    fit_seconds: float
    serialized_bytes: int
    warnings: tuple[str, ...] = ()


def _as_2d(values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return array[:, None] if array.ndim == 1 else array


def _bootstrap_indices(data: PreparedTrainingData, rng: np.random.Generator) -> np.ndarray:
    groups = list(data.split.train_groups)
    sampled = rng.choice(groups, size=len(groups), replace=True)
    return np.concatenate([np.flatnonzero(data.group_values == group) for group in sampled])


def _fit_linear(data: PreparedTrainingData, *, seed: int, members: int) -> _FittedFamily:
    started = perf_counter()
    design = np.column_stack((np.ones(len(data.x)), data.x))
    rng = np.random.default_rng(seed)
    fitted: list[np.ndarray] = []
    for _ in range(members):
        indices = _bootstrap_indices(data, rng)
        fitted.append(
            np.linalg.lstsq(design[indices], data.normalized_y[indices], rcond=None)[0]
        )
    coefficients = np.stack(fitted)
    fit_seconds = perf_counter() - started

    def predict_members(points: np.ndarray) -> np.ndarray:
        point_design = np.column_stack((np.ones(len(points)), points))
        return np.stack([point_design @ coefficient for coefficient in coefficients])

    return _FittedFamily(
        config={
            "ensemble_size": members,
            "fit": "bootstrap ordinary least squares",
            "output_coupling": "shared features and bootstrap; column-separable fit",
        },
        predict_members=predict_members,
        fit_seconds=fit_seconds,
        serialized_bytes=len(pickle.dumps(coefficients, protocol=5)),
    )


def _fit_trees(data: PreparedTrainingData, *, seed: int, tree_count: int) -> _FittedFamily:
    model = ExtraTreesRegressor(
        n_estimators=tree_count,
        min_samples_leaf=2,
        max_features=1.0,
        bootstrap=True,
        random_state=seed,
        n_jobs=1,
    )
    started = perf_counter()
    train_targets = data.normalized_y[data.train_mask]
    model.fit(
        data.x[data.train_mask],
        train_targets.ravel() if train_targets.shape[1] == 1 else train_targets,
    )
    fit_seconds = perf_counter() - started

    def predict_members(points: np.ndarray) -> np.ndarray:
        return np.stack([_as_2d(estimator.predict(points)) for estimator in model.estimators_])

    return _FittedFamily(
        config={
            "estimator": "ExtraTreesRegressor",
            "tree_count": tree_count,
            "min_samples_leaf": 2,
            "bootstrap": True,
            "output_coupling": "shared tree splits across objective outputs",
        },
        predict_members=predict_members,
        fit_seconds=fit_seconds,
        serialized_bytes=len(pickle.dumps(model, protocol=5)),
    )


def _fit_mlp(
    data: PreparedTrainingData,
    *,
    seed: int,
    members: int,
    hidden_width: int,
    max_iter: int,
) -> _FittedFamily:
    started = perf_counter()
    scaler = StandardScaler().fit(data.x[data.train_mask])
    scaled = scaler.transform(data.x)
    rng = np.random.default_rng(seed)
    models: list[MLPRegressor] = []
    warning_messages: list[str] = []
    for member in range(members):
        indices = _bootstrap_indices(data, rng)
        model = MLPRegressor(
            hidden_layer_sizes=(hidden_width,),
            activation="relu",
            # L-BFGS is the deliberately small-data baseline; Adam is intended for larger traces.
            solver="lbfgs",
            alpha=1e-4,
            max_iter=max_iter,
            random_state=seed + member,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            targets = data.normalized_y[indices]
            model.fit(
                scaled[indices],
                targets.ravel() if targets.shape[1] == 1 else targets,
            )
        warning_messages.extend(str(item.message) for item in caught)
        models.append(model)
    fit_seconds = perf_counter() - started

    def predict_members(points: np.ndarray) -> np.ndarray:
        transformed = scaler.transform(points)
        return np.stack([_as_2d(model.predict(transformed)) for model in models])

    return _FittedFamily(
        config={
            "estimator": "MLPRegressor",
            "ensemble_size": members,
            "hidden_layer_sizes": [hidden_width],
            "activation": "relu",
            "solver": "lbfgs",
            "max_iter": max_iter,
            "input_standardization": True,
            "output_coupling": "shared hidden layer with per-objective output units",
        },
        predict_members=predict_members,
        fit_seconds=fit_seconds,
        serialized_bytes=len(pickle.dumps((scaler, models), protocol=5)),
        warnings=tuple(warning_messages),
    )


def _percentile(values: list[float], probability: float) -> float:
    return float(np.quantile(np.asarray(values), probability))


def _latency(
    predict_members: Callable[[np.ndarray], np.ndarray],
    points: np.ndarray,
    repeats: int,
) -> dict[str, float]:
    predict_members(points)  # Excluded warmup: imports, allocation, and lazy setup are not timed.
    durations: list[float] = []
    for _ in range(repeats):
        started = perf_counter()
        predict_members(points).mean(axis=0)
        durations.append(perf_counter() - started)
    count = len(points)
    return {
        "warm_batch_p50_seconds": median(durations),
        "warm_batch_p95_seconds": _percentile(durations, 0.95),
        "warm_item_p50_seconds": median(durations) / count,
        "warm_item_p95_seconds": _percentile(durations, 0.95) / count,
    }


def _error_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, list[float]]:
    absolute = np.abs(actual - predicted)
    return {
        "mae": absolute.mean(axis=0).tolist(),
        "rmse": np.sqrt(np.mean(np.square(absolute), axis=0)).tolist(),
        "max_error": absolute.max(axis=0).tolist(),
        "rank_correlation": _rank_correlations(actual, predicted),
    }


def _accepted_error_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    accepted: np.ndarray,
    ranges: np.ndarray,
) -> dict[str, list[float] | list[float | None] | None]:
    if not accepted.any():
        missing: list[float | None] = [None] * int(actual.shape[1])
        return {
            "mae": None,
            "mae_q95_q05_fraction": missing,
            "max_error": None,
        }
    absolute = np.abs(actual[accepted] - predicted[accepted])
    return {
        "mae": absolute.mean(axis=0).tolist(),
        "mae_q95_q05_fraction": _normalized_mae(
            actual[accepted], predicted[accepted], ranges
        ),
        "max_error": absolute.max(axis=0).tolist(),
    }


def _evaluate_family(
    family: _FittedFamily,
    data: PreparedTrainingData,
    *,
    latency_repeats: int,
) -> dict[str, Any]:
    normalized_member_predictions = family.predict_members(data.x)
    normalized_prediction = normalized_member_predictions.mean(axis=0)
    prediction = normalized_prediction * data.output_scales
    uncertainty = normalized_member_predictions.std(axis=0).max(axis=1)
    center = data.x[data.train_mask].mean(axis=0)
    scale = np.maximum(data.x[data.train_mask].std(axis=0), 1e-6)
    support = np.sqrt(np.mean(np.square((data.x - center) / scale), axis=1))
    support_threshold = _quantile(support[data.calibration_mask], 0.99)
    uncertainty_threshold = _quantile(uncertainty[data.calibration_mask], 0.99)
    in_range = np.all(
        np.isfinite(normalized_prediction)
        & (normalized_prediction >= 0.0)
        & (normalized_prediction <= 1.0),
        axis=1,
    )
    accepted = (
        in_range
        & (support <= support_threshold)
        & (uncertainty <= uncertainty_threshold)
    )
    audit = data.audit_mask
    audit_prediction = prediction[audit]
    audit_actual = data.y[audit]
    audit_ranges = _q95_q05_ranges(audit_actual)
    audit_accepted = accepted[audit]
    curve = []
    for probability in (0.50, 0.75, 0.90, 0.95, 0.99):
        threshold = _quantile(uncertainty[data.calibration_mask], probability)
        selected = in_range[audit] & (support[audit] <= support_threshold) & (
            uncertainty[audit] <= threshold
        )
        curve.append(
            {
                "calibration_quantile": probability,
                "uncertainty_threshold": threshold,
                "audit_coverage": float(np.mean(selected)),
                "audit_mae": _accepted_error_metrics(
                    audit_actual,
                    audit_prediction,
                    selected,
                    audit_ranges,
                )["mae"],
            }
        )
    return {
        "config": family.config,
        "fit_seconds": family.fit_seconds,
        "estimated_serialized_bytes": family.serialized_bytes,
        "fit_warnings": list(family.warnings),
        "calibration": {
            **_error_metrics(
                data.y[data.calibration_mask],
                prediction[data.calibration_mask],
            ),
            "support_threshold": support_threshold,
            "uncertainty_threshold": uncertainty_threshold,
        },
        "audit": {
            **_error_metrics(audit_actual, audit_prediction),
            "score_q05": np.quantile(audit_actual, 0.05, axis=0).tolist(),
            "score_q95": np.quantile(audit_actual, 0.95, axis=0).tolist(),
            "score_q95_q05_range": audit_ranges.tolist(),
            "support_coverage": float(np.mean(support[audit] <= support_threshold)),
            "uncertainty_coverage": float(
                np.mean(uncertainty[audit] <= uncertainty_threshold)
            ),
            "in_range_fraction": float(np.mean(in_range[audit])),
            "selective_coverage": float(np.mean(audit_accepted)),
            "accepted_error": _accepted_error_metrics(
                audit_actual,
                audit_prediction,
                audit_accepted,
                audit_ranges,
            ),
            "selective_risk_curve": curve,
        },
        "inference_latency": _latency(
            family.predict_members,
            data.x[data.audit_mask],
            latency_repeats,
        ),
    }


def compare_model_families(
    samples: tuple[TeacherSample, ...],
    *,
    output_labels: tuple[str, ...],
    trace_paths: tuple[Path, ...],
    schemas: tuple[SequenceFeatureSchema, ...] | None = None,
    output_normalizations: tuple[OutputNormalization, ...] = (),
    seed: int = 0,
    linear_ensemble_size: int = 8,
    tree_count: int = 64,
    mlp_ensemble_size: int = 5,
    mlp_hidden_width: int = 32,
    mlp_max_iter: int = 300,
    latency_repeats: int = 20,
) -> dict[str, Any]:
    """Compare three vector-output families without packaging or selecting a runtime model."""

    if min(linear_ensemble_size, tree_count, mlp_ensemble_size, latency_repeats) < 2:
        raise ValueError("ensemble sizes, tree count, and latency repeats must be at least 2")
    if mlp_hidden_width < 1 or mlp_max_iter < 1:
        raise ValueError("MLP width and iterations must be positive")
    prepared = prepare_training_data(
        samples,
        output_labels=output_labels,
        trace_paths=trace_paths,
        schemas=schemas,
        output_normalizations=output_normalizations,
        seed=seed,
    )
    families = {
        "linear_ensemble": _fit_linear(
            prepared,
            seed=seed,
            members=linear_ensemble_size,
        ),
        "extra_trees": _fit_trees(prepared, seed=seed, tree_count=tree_count),
        "small_mlp_ensemble": _fit_mlp(
            prepared,
            seed=seed,
            members=mlp_ensemble_size,
            hidden_width=mlp_hidden_width,
            max_iter=mlp_max_iter,
        ),
    }
    return {
        "schema_version": "1.0",
        "experiment": {
            "comparison_only": True,
            "same_grouped_split": True,
            "vector_outputs": True,
            "scalarized_objective": False,
            "automatic_winner": None,
            "selection_rule": (
                "Choose the simplest family that meets predeclared per-objective accuracy, "
                "selective coverage, and warm-latency thresholds, then run paired optimization."
            ),
        },
        "libraries": {"numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "dataset": {
            "samples": len(samples),
            "features": int(prepared.x.shape[1]),
            "output_labels": list(output_labels),
            "output_normalizations": [
                normalization.model_dump(mode="json")
                for normalization in prepared.output_normalizations
            ],
            "split": prepared.split.model_dump(mode="json"),
            "feature_schemas": [schema.model_dump(mode="json") for schema in prepared.schemas],
        },
        "models": {
            name: _evaluate_family(family, prepared, latency_repeats=latency_repeats)
            for name, family in families.items()
        },
    }
