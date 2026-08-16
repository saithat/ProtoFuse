"""Reproducible grouped training for the first portable fusion baseline."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from protofuse.sai.artifacts import (
    FusionManifest,
    LoadedFusionArtifact,
    file_sha256,
    write_unreviewed_fusion_artifact,
)
from protofuse.sai.model import (
    LinearEnsembleModel,
    OutputNormalization,
    SequenceFeatureSchema,
    featurize_inputs,
)
from protofuse.sai.signatures import program_signature, step_group_signature
from protofuse.sai.tracing import TraceRow


@dataclass(frozen=True)
class TeacherSample:
    sequences: tuple[str, ...]
    outputs: tuple[float, ...]
    group_id: str
    output_target_bins: tuple[int | None, ...] = ()


class SplitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    seed: int
    trace_sha256: tuple[str, ...]
    input_sha256: tuple[str, ...] = ()
    train_groups: tuple[str, ...]
    calibration_groups: tuple[str, ...]
    audit_groups: tuple[str, ...]
    train_samples: int
    calibration_samples: int
    audit_samples: int


@dataclass(frozen=True)
class TrainingResult:
    model: LinearEnsembleModel
    split: SplitManifest
    metrics: dict[str, Any]


@dataclass(frozen=True)
class PreparedTrainingData:
    """One feature matrix and one leakage-resistant split shared by every model family."""

    schemas: tuple[SequenceFeatureSchema, ...]
    output_normalizations: tuple[OutputNormalization, ...]
    x: np.ndarray
    y: np.ndarray
    normalized_y: np.ndarray
    output_scales: np.ndarray
    group_values: np.ndarray
    train_mask: np.ndarray
    calibration_mask: np.ndarray
    audit_mask: np.ndarray
    split: SplitManifest


def _read_trace(path: Path) -> list[TraceRow]:
    rows: list[TraceRow] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(TraceRow.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"invalid trace row {path}:{line_number}: {exc}") from exc
    return rows


def validate_teacher_trace_contract(
    trace_paths: tuple[Path, ...],
    *,
    program: Any,
    optimizer_index: int,
    constraint_labels: tuple[str, ...],
) -> None:
    """Fail closed when teacher rows do not match the frozen program group."""

    signature = step_group_signature(
        program,
        optimizer_index=optimizer_index,
        constraint_labels=constraint_labels,
    )
    expected_program_sha256 = program_signature(program).sha256
    expected_by_label = {constraint.label: constraint for constraint in signature.constraints}
    seen_labels: set[str] = set()
    trace_schemas: set[str] = set()
    for path in trace_paths:
        for row in _read_trace(path):
            if (
                row.optimizer_index != optimizer_index
                or row.constraint_label not in expected_by_label
            ):
                continue
            trace_schemas.add(row.schema_version)
            expected = expected_by_label[row.constraint_label]
            expected_identity = (
                expected.function.identity if expected.function is not None else None
            )
            if (
                row.constraint_identity != expected_identity
                or row.constraint_config != expected.function_config
                or row.constraint_threshold != expected.threshold
                or row.constraint_weight != expected.weight
            ):
                raise ValueError(
                    f"teacher trace contract differs for constraint {row.constraint_label!r}"
                )
            if row.schema_version == "1.1" and row.program_sha256 != expected_program_sha256:
                raise ValueError("teacher trace full-program contract differs")
            seen_labels.add(row.constraint_label)
    if len(trace_schemas) > 1:
        raise ValueError("teacher traces mix legacy and full-contract trace schemas")
    missing = sorted(set(constraint_labels) - seen_labels)
    if missing:
        raise ValueError(f"teacher traces contain no rows for constraints: {missing}")


def _target_bins(row: TraceRow) -> int | None:
    metadata = row.metadata
    if not isinstance(metadata, Mapping) or "paper_target_bins" not in metadata:
        return None
    value = metadata["paper_target_bins"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"constraint {row.constraint_label!r} has invalid paper_target_bins metadata"
        )
    return int(value)


def load_teacher_samples(
    trace_paths: tuple[Path, ...],
    *,
    optimizer_index: int,
    constraint_labels: tuple[str, ...],
) -> tuple[TeacherSample, ...]:
    """Align separate objective rows into one vector target for each proposal occurrence."""

    if not constraint_labels or len(set(constraint_labels)) != len(constraint_labels):
        raise ValueError("constraint_labels must be non-empty and unique")
    buckets: dict[
        tuple[str, str, int, tuple[str, ...]],
        dict[str, list[TraceRow]],
    ] = defaultdict(lambda: defaultdict(list))
    requested = set(constraint_labels)
    for path in trace_paths:
        for row in _read_trace(path):
            if row.optimizer_index != optimizer_index or row.constraint_label not in requested:
                continue
            if row.error is not None or row.score is None or row.input_sequences is None:
                raise ValueError(
                    f"teacher trace contains failed or incomplete row for {row.constraint_label!r}"
                )
            if row.has_structures or row.has_logits:
                raise ValueError(
                    "score-only training cannot replace structure/logit-producing outputs"
                )
            key = (row.run_id, row.group_id, row.optimizer_index, row.input_sha256)
            buckets[key][row.constraint_label].append(row)

    samples: list[TeacherSample] = []
    for key in sorted(buckets):
        per_label = buckets[key]
        missing = [label for label in constraint_labels if label not in per_label]
        if missing:
            raise ValueError(f"teacher objective group is incomplete or unequal; missing {missing}")
        occurrence_counts = {len(per_label[label]) for label in constraint_labels}
        if len(occurrence_counts) != 1:
            raise ValueError("teacher objective group is incomplete or unequal")
        [occurrences] = occurrence_counts
        for occurrence in range(occurrences):
            rows = [per_label[label][occurrence] for label in constraint_labels]
            sequences = rows[0].input_sequences
            if sequences is None or any(row.input_sequences != sequences for row in rows):
                raise ValueError("joined teacher objectives disagree on input sequences")
            provenance = (
                rows[0].program_sha256,
                rows[0].program_seed,
                rows[0].collection_id,
                rows[0].program_id,
                rows[0].methodology_id,
                rows[0].tier,
                rows[0].input_structure_sha256,
                rows[0].proposal_index,
            )
            if any(
                (
                    row.program_sha256,
                    row.program_seed,
                    row.collection_id,
                    row.program_id,
                    row.methodology_id,
                    row.tier,
                    row.input_structure_sha256,
                    row.proposal_index,
                )
                != provenance
                for row in rows[1:]
            ):
                raise ValueError("joined teacher objectives disagree on trace provenance")
            samples.append(
                TeacherSample(
                    sequences=sequences,
                    outputs=tuple(float(row.score) for row in rows if row.score is not None),
                    group_id=key[1],
                    output_target_bins=tuple(_target_bins(row) for row in rows),
                )
            )
    if not samples:
        raise ValueError("no complete teacher samples found for requested constraint group")
    return tuple(samples)


def infer_feature_schemas(samples: tuple[TeacherSample, ...]) -> tuple[SequenceFeatureSchema, ...]:
    schemas: list[SequenceFeatureSchema] = []
    input_count = len(samples[0].sequences)
    if any(len(sample.sequences) != input_count for sample in samples):
        raise ValueError("teacher samples have inconsistent input counts")
    for input_index in range(input_count):
        sequences = [sample.sequences[input_index] for sample in samples]
        symbols = set().union(*(set(sequence) for sequence in sequences))
        lengths = {len(sequence) for sequence in sequences}
        if symbols <= set("ACGT"):
            alphabet = "ACGT"
            sequence_type = "dna"
            kmer_size = 3
            stride = 3
        else:
            alphabet = "ACDEFGHIKLMNPQRSTVWY"
            sequence_type = "protein"
            kmer_size = 1
            stride = 1
        if not symbols <= set(alphabet):
            raise ValueError(f"cannot infer a supported alphabet for symbols {sorted(symbols)}")
        schemas.append(
            SequenceFeatureSchema(
                sequence_type=sequence_type,
                alphabet=alphabet,
                kmer_size=kmer_size,
                stride=stride,
                # Protein 1-mer frequencies already are composition; emitting both
                # made the old 40-column representation only 20 unique signals.
                include_composition=sequence_type != "protein",
                expected_length=next(iter(lengths)) if len(lengths) == 1 else None,
                position_encoding=(
                    "one_hot" if sequence_type == "protein" and len(lengths) == 1 else "none"
                ),
            )
        )
    return tuple(schemas)


def _split_groups(groups: set[str], seed: int) -> tuple[set[str], set[str], set[str]]:
    if len(groups) < 3:
        raise ValueError("training requires at least three leakage-resistant group IDs")
    ordered = sorted(groups, key=lambda item: sha256(f"{seed}:{item}".encode()).hexdigest())
    calibration_count = max(1, round(len(ordered) * 0.2))
    audit_count = max(1, round(len(ordered) * 0.2))
    train_count = len(ordered) - calibration_count - audit_count
    if train_count < 1:
        train_count = 1
        calibration_count = 1
        audit_count = len(ordered) - 2
    train = set(ordered[:train_count])
    calibration = set(ordered[train_count : train_count + calibration_count])
    audit = set(ordered[train_count + calibration_count :])
    return train, calibration, audit


def _sample_input_sha256(sequences: tuple[str, ...]) -> str:
    digest = sha256()
    for sequence in sequences:
        encoded = sequence.encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def prepare_training_data(
    samples: tuple[TeacherSample, ...],
    *,
    output_labels: tuple[str, ...],
    trace_paths: tuple[Path, ...],
    schemas: tuple[SequenceFeatureSchema, ...] | None = None,
    output_normalizations: tuple[OutputNormalization, ...] = (),
    seed: int = 0,
) -> PreparedTrainingData:
    """Featurize once and freeze the exact grouped split used by model comparisons."""

    if not samples or not output_labels:
        raise ValueError("training requires samples and at least one output label")
    if any(len(sample.outputs) != len(output_labels) for sample in samples):
        raise ValueError("teacher output dimensions do not match output labels")
    groups_by_input: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        groups_by_input[_sample_input_sha256(sample.sequences)].add(sample.group_id)
    cross_group_duplicates = sorted(
        digest for digest, groups in groups_by_input.items() if len(groups) > 1
    )
    if cross_group_duplicates:
        raise ValueError(
            "identical teacher inputs span multiple group IDs; grouped splitting would leak"
        )
    resolved_normalizations = output_normalizations or tuple(
        OutputNormalization() for _ in output_labels
    )
    if len(resolved_normalizations) != len(output_labels):
        raise ValueError("output normalization dimension does not match output labels")
    for sample in samples:
        for output_index, normalization in enumerate(resolved_normalizations):
            computed_bins = normalization.sequence_bin_count(sample.sequences)
            if computed_bins is None:
                continue
            if len(sample.output_target_bins) != len(output_labels):
                raise ValueError(
                    "sequence-bin normalization requires paper_target_bins trace metadata"
                )
            recorded_bins = sample.output_target_bins[output_index]
            if recorded_bins != computed_bins:
                raise ValueError(
                    "paper_target_bins metadata does not match the frozen sequence-bin rule"
                )
    resolved_schemas = schemas or infer_feature_schemas(samples)
    x = np.asarray(
        [featurize_inputs(sample.sequences, resolved_schemas) for sample in samples],
        dtype=np.float64,
    )
    y = np.asarray([sample.outputs for sample in samples], dtype=np.float64)
    if not np.all(np.isfinite(y)):
        raise ValueError("teacher outputs must be finite")
    output_scales = np.asarray(
        [
            [normalization.scale(sample.sequences) for normalization in resolved_normalizations]
            for sample in samples
        ],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(output_scales)) or np.any(output_scales <= 0.0):
        raise ValueError("teacher output normalization scales must be positive and finite")
    normalized_y = y / output_scales
    if not np.all(np.isfinite(normalized_y)) or np.any((normalized_y < 0.0) | (normalized_y > 1.0)):
        raise ValueError("normalized teacher outputs must be finite and in [0, 1]")

    train_groups, calibration_groups, audit_groups = _split_groups(
        {sample.group_id for sample in samples},
        seed,
    )
    group_values = np.asarray([sample.group_id for sample in samples])
    train_mask = np.asarray([group in train_groups for group in group_values])
    calibration_mask = np.asarray([group in calibration_groups for group in group_values])
    audit_mask = np.asarray([group in audit_groups for group in group_values])
    if not train_mask.any() or not calibration_mask.any() or not audit_mask.any():
        raise ValueError("group split produced an empty cohort")
    split = SplitManifest(
        seed=seed,
        trace_sha256=tuple(file_sha256(path) for path in trace_paths),
        input_sha256=tuple(sorted(groups_by_input)),
        train_groups=tuple(sorted(train_groups)),
        calibration_groups=tuple(sorted(calibration_groups)),
        audit_groups=tuple(sorted(audit_groups)),
        train_samples=int(train_mask.sum()),
        calibration_samples=int(calibration_mask.sum()),
        audit_samples=int(audit_mask.sum()),
    )
    return PreparedTrainingData(
        schemas=resolved_schemas,
        output_normalizations=resolved_normalizations,
        x=x,
        y=y,
        normalized_y=normalized_y,
        output_scales=output_scales,
        group_values=group_values,
        train_mask=train_mask,
        calibration_mask=calibration_mask,
        audit_mask=audit_mask,
        split=split,
    )


def _quantile(values: np.ndarray, probability: float) -> float:
    return float(np.quantile(values, probability, method="higher"))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def _rank_correlations(actual: np.ndarray, predicted: np.ndarray) -> list[float | None]:
    correlations: list[float | None] = []
    for output_index in range(actual.shape[1]):
        actual_ranks = _average_ranks(actual[:, output_index])
        predicted_ranks = _average_ranks(predicted[:, output_index])
        actual_centered = actual_ranks - actual_ranks.mean()
        predicted_centered = predicted_ranks - predicted_ranks.mean()
        denominator = float(
            np.sqrt(np.sum(np.square(actual_centered)) * np.sum(np.square(predicted_centered)))
        )
        correlations.append(
            float(np.sum(actual_centered * predicted_centered) / denominator)
            if denominator > 0.0
            else None
        )
    return correlations


def _q95_q05_ranges(values: np.ndarray) -> np.ndarray:
    """Return robust per-output ranges used to make unlike objectives comparable."""

    return np.asarray(
        np.quantile(values, 0.95, axis=0) - np.quantile(values, 0.05, axis=0),
        dtype=np.float64,
    )


def _normalized_mae(
    actual: np.ndarray,
    predicted: np.ndarray,
    ranges: np.ndarray,
) -> list[float | None]:
    if len(actual) == 0:
        return [None] * int(predicted.shape[1])
    mae = np.abs(actual - predicted).mean(axis=0)
    return [
        float(error / span) if math.isfinite(float(span)) and span > 0.0 else None
        for error, span in zip(mae, ranges, strict=True)
    ]


def _training_result_from_coefficients(
    prepared: PreparedTrainingData,
    *,
    output_labels: tuple[str, ...],
    coefficients: list[np.ndarray],
    fit_method: Literal["ols", "ridge"],
    ridge_alpha: tuple[float, ...] = (),
    ridge_standardize_features: tuple[bool, ...] = (),
    reject_unseen_features: bool = False,
    smooth_support_scale: bool = False,
    extra_metrics: Mapping[str, Any] | None = None,
) -> TrainingResult:
    """Calibrate and package one already-fitted coefficient ensemble."""

    if not coefficients:
        raise ValueError("coefficient ensemble cannot be empty")
    x = prepared.x
    y = prepared.y
    output_scales = prepared.output_scales
    train_mask = prepared.train_mask
    calibration_mask = prepared.calibration_mask
    audit_mask = prepared.audit_mask
    design = np.column_stack((np.ones(len(x)), x))
    normalized_stacked = np.stack([design @ coefficient for coefficient in coefficients])
    normalized_prediction = normalized_stacked.mean(axis=0)
    normalized_uncertainty = normalized_stacked.std(axis=0)
    prediction = normalized_prediction * output_scales
    center = x[train_mask].mean(axis=0)
    scale = np.maximum(x[train_mask].std(axis=0), 1e-6)
    if smooth_support_scale:
        scale = np.maximum(scale, 0.5 / math.sqrt(int(train_mask.sum()) + 1.0))
    feature_seen = np.any(np.abs(x[train_mask]) > 1e-12, axis=0)
    unseen = (
        np.any((np.abs(x) > 1e-12) & ~feature_seen, axis=1)
        if reject_unseen_features
        else np.zeros(len(x), dtype=np.bool_)
    )
    support = np.sqrt(np.mean(np.square((x - center) / scale), axis=1))
    supported_calibration = calibration_mask & ~unseen
    if not supported_calibration.any():
        raise ValueError("calibration contains no samples supported by the training categories")
    support_threshold = _quantile(support[supported_calibration], 0.99)
    support[unseen] = support_threshold + max(1.0, support_threshold * 1e-6)
    uncertainty_threshold = _quantile(
        normalized_uncertainty[supported_calibration].max(axis=1),
        0.99,
    )
    calibration_error = np.abs(y[calibration_mask] - prediction[calibration_mask])
    supported_calibration_error = np.abs(
        y[supported_calibration] - prediction[supported_calibration]
    )
    error_quantiles = tuple(
        _quantile(supported_calibration_error[:, output_index], 0.99)
        for output_index in range(len(output_labels))
    )
    model = LinearEnsembleModel(
        input_schemas=prepared.schemas,
        output_labels=output_labels,
        output_normalizations=prepared.output_normalizations,
        coefficients=tuple(
            tuple(tuple(float(value) for value in row) for row in coefficient)
            for coefficient in coefficients
        ),
        fit_method=fit_method,
        ridge_alpha=ridge_alpha,
        ridge_standardize_features=ridge_standardize_features,
        feature_center=tuple(float(value) for value in center),
        feature_scale=tuple(float(value) for value in scale),
        reject_unseen_features=reject_unseen_features,
        feature_seen=(
            tuple(bool(value) for value in feature_seen) if reject_unseen_features else ()
        ),
        support_threshold=support_threshold,
        uncertainty_threshold=uncertainty_threshold,
        calibration_absolute_error=error_quantiles,
    )
    audit_error = np.abs(y[audit_mask] - prediction[audit_mask])
    audit_prediction = prediction[audit_mask]
    audit_normalized_uncertainty = normalized_uncertainty[audit_mask].max(axis=1)
    audit_support = support[audit_mask]
    audit_in_range = np.all(
        np.isfinite(normalized_prediction[audit_mask])
        & (normalized_prediction[audit_mask] >= 0.0)
        & (normalized_prediction[audit_mask] <= 1.0),
        axis=1,
    )
    audit_accepted = (
        audit_in_range
        & (audit_support <= support_threshold)
        & (audit_normalized_uncertainty <= uncertainty_threshold)
    )
    accepted_error = audit_error[audit_accepted]
    audit_actual = y[audit_mask]
    audit_ranges = _q95_q05_ranges(audit_actual)
    accepted_actual = audit_actual[audit_accepted]
    accepted_prediction = audit_prediction[audit_accepted]
    metrics = {
        "fit_method": fit_method,
        "ridge_alpha": list(ridge_alpha),
        "ridge_standardize_features": list(ridge_standardize_features),
        "calibration_mae": calibration_error.mean(axis=0).tolist(),
        "calibration_rmse": np.sqrt(np.mean(np.square(calibration_error), axis=0)).tolist(),
        "calibration_max_error": calibration_error.max(axis=0).tolist(),
        "audit_mae": audit_error.mean(axis=0).tolist(),
        "audit_rmse": np.sqrt(np.mean(np.square(audit_error), axis=0)).tolist(),
        "audit_max_error": audit_error.max(axis=0).tolist(),
        "audit_rank_correlation": _rank_correlations(audit_actual, audit_prediction),
        "audit_score_q05": np.quantile(audit_actual, 0.05, axis=0).tolist(),
        "audit_score_q95": np.quantile(audit_actual, 0.95, axis=0).tolist(),
        "audit_score_q95_q05_range": audit_ranges.tolist(),
        "audit_support_coverage": float(np.mean(audit_support <= support_threshold)),
        "audit_uncertainty_coverage": float(
            np.mean(audit_normalized_uncertainty <= uncertainty_threshold)
        ),
        "audit_selective_coverage": float(np.mean(audit_accepted)),
        "audit_unseen_feature_rejections": int(unseen[audit_mask].sum()),
        "audit_accepted_mae": (
            accepted_error.mean(axis=0).tolist() if len(accepted_error) else None
        ),
        "audit_accepted_mae_q95_q05_fraction": _normalized_mae(
            accepted_actual,
            accepted_prediction,
            audit_ranges,
        ),
        "audit_accepted_max_error": (
            accepted_error.max(axis=0).tolist() if len(accepted_error) else None
        ),
    }
    if extra_metrics:
        metrics.update(extra_metrics)
    return TrainingResult(model=model, split=prepared.split, metrics=metrics)


def train_linear_ensemble(
    samples: tuple[TeacherSample, ...],
    *,
    output_labels: tuple[str, ...],
    trace_paths: tuple[Path, ...],
    schemas: tuple[SequenceFeatureSchema, ...] | None = None,
    output_normalizations: tuple[OutputNormalization, ...] = (),
    seed: int = 0,
    ensemble_size: int = 8,
) -> TrainingResult:
    if ensemble_size < 2:
        raise ValueError("ensemble_size must be at least 2")
    prepared = prepare_training_data(
        samples,
        output_labels=output_labels,
        trace_paths=trace_paths,
        schemas=schemas,
        output_normalizations=output_normalizations,
        seed=seed,
    )
    design = np.column_stack((np.ones(len(prepared.x)), prepared.x))
    rng = np.random.default_rng(seed)
    train_group_list = list(prepared.split.train_groups)
    coefficients: list[np.ndarray] = []
    for _ in range(ensemble_size):
        sampled_groups = rng.choice(
            train_group_list,
            size=len(train_group_list),
            replace=True,
        )
        indices = np.concatenate(
            [np.flatnonzero(prepared.group_values == group) for group in sampled_groups]
        )
        # The vector solve is a compact multi-output implementation, but ordinary least squares
        # remains column-separable: it does not learn cross-objective covariance.
        coefficients.append(
            np.linalg.lstsq(
                design[indices],
                prepared.normalized_y[indices],
                rcond=None,
            )[0]
        )
    return _training_result_from_coefficients(
        prepared,
        output_labels=output_labels,
        coefficients=coefficients,
        fit_method="ols",
    )


def _fit_ridge_column(
    x: np.ndarray,
    y: np.ndarray,
    *,
    alpha: float,
    standardize_features: bool,
) -> np.ndarray:
    """Fit ridge with an unpenalized intercept and return raw-feature coefficients."""

    center = x.mean(axis=0)
    y_center = float(y.mean())
    scale = (
        np.maximum(x.std(axis=0), 1e-6)
        if standardize_features
        else np.ones(x.shape[1], dtype=np.float64)
    )
    centered = (x - center) / scale
    gram = centered.T @ centered
    right = centered.T @ (y - y_center)
    scaled_coefficients = np.linalg.solve(
        gram + alpha * np.eye(x.shape[1], dtype=np.float64),
        right,
    )
    coefficients = scaled_coefficients / scale
    intercept = y_center - float(center @ coefficients)
    return np.concatenate(([intercept], coefficients))


def _fit_ridge_matrix(
    x: np.ndarray,
    y: np.ndarray,
    *,
    alphas: tuple[float, ...],
    standardize_features: tuple[bool, ...],
) -> np.ndarray:
    return np.column_stack(
        [
            _fit_ridge_column(
                x,
                y[:, output_index],
                alpha=alphas[output_index],
                standardize_features=standardize_features[output_index],
            )
            for output_index in range(y.shape[1])
        ]
    )


def _ridge_inner_cv(
    prepared: PreparedTrainingData,
    *,
    seed: int,
    alpha_grid: tuple[float, ...],
) -> tuple[tuple[float, ...], tuple[bool, ...], tuple[float, ...]]:
    train_groups = sorted(
        prepared.split.train_groups,
        key=lambda group: sha256(f"ridge-cv:{seed}:{group}".encode()).hexdigest(),
    )
    fold_count = min(5, len(train_groups))
    if fold_count < 2:
        raise ValueError("ridge selection requires at least two training groups")
    folds = tuple(set(train_groups[index::fold_count]) for index in range(fold_count))
    selected_alpha: list[float] = []
    selected_standardization: list[bool] = []
    selected_mae: list[float] = []
    for output_index in range(prepared.normalized_y.shape[1]):
        candidates: list[tuple[float, bool, float]] = []
        for standardize in (False, True):
            for alpha in alpha_grid:
                absolute_error = 0.0
                observations = 0
                for heldout_groups in folds:
                    heldout = (
                        np.asarray([group in heldout_groups for group in prepared.group_values])
                        & prepared.train_mask
                    )
                    inner_train = prepared.train_mask & ~heldout
                    coefficient = _fit_ridge_column(
                        prepared.x[inner_train],
                        prepared.normalized_y[inner_train, output_index],
                        alpha=alpha,
                        standardize_features=standardize,
                    )
                    prediction = (
                        np.column_stack((np.ones(int(heldout.sum())), prepared.x[heldout]))
                        @ coefficient
                    )
                    absolute_error += float(
                        np.abs(prepared.normalized_y[heldout, output_index] - prediction).sum()
                    )
                    observations += int(heldout.sum())
                candidates.append((absolute_error / observations, standardize, alpha))
        mae, standardize, alpha = min(
            candidates,
            key=lambda candidate: (candidate[0], candidate[1], candidate[2]),
        )
        selected_alpha.append(alpha)
        selected_standardization.append(standardize)
        selected_mae.append(mae)
    return (
        tuple(selected_alpha),
        tuple(selected_standardization),
        tuple(selected_mae),
    )


def train_ridge_ensemble(
    samples: tuple[TeacherSample, ...],
    *,
    output_labels: tuple[str, ...],
    trace_paths: tuple[Path, ...],
    schemas: tuple[SequenceFeatureSchema, ...],
    output_normalizations: tuple[OutputNormalization, ...] = (),
    seed: int = 0,
    ensemble_size: int = 8,
    alpha_grid: tuple[float, ...] = (
        0.0001,
        0.001,
        0.01,
        0.1,
        1.0,
        3.1622776601683795,
        10.0,
        100.0,
    ),
) -> TrainingResult:
    """Fit objective-specific ridge columns with grouped CV and bootstrap uncertainty."""

    if ensemble_size < 2:
        raise ValueError("ensemble_size must be at least 2")
    if not alpha_grid or any(alpha <= 0.0 or not math.isfinite(alpha) for alpha in alpha_grid):
        raise ValueError("ridge alpha grid must contain positive finite values")
    prepared = prepare_training_data(
        samples,
        output_labels=output_labels,
        trace_paths=trace_paths,
        schemas=schemas,
        output_normalizations=output_normalizations,
        seed=seed,
    )
    alphas, standardize, inner_cv_mae = _ridge_inner_cv(
        prepared,
        seed=seed,
        alpha_grid=alpha_grid,
    )
    full = _fit_ridge_matrix(
        prepared.x[prepared.train_mask],
        prepared.normalized_y[prepared.train_mask],
        alphas=alphas,
        standardize_features=standardize,
    )
    rng = np.random.default_rng(seed)
    train_groups = list(prepared.split.train_groups)
    bootstrap: list[np.ndarray] = []
    for _ in range(ensemble_size):
        sampled_groups = rng.choice(train_groups, size=len(train_groups), replace=True)
        indices = np.concatenate(
            [np.flatnonzero(prepared.group_values == group) for group in sampled_groups]
        )
        bootstrap.append(
            _fit_ridge_matrix(
                prepared.x[indices],
                prepared.normalized_y[indices],
                alphas=alphas,
                standardize_features=standardize,
            )
        )
    bootstrap_mean = np.mean(np.stack(bootstrap), axis=0)
    recentered = [full + coefficient - bootstrap_mean for coefficient in bootstrap]
    return _training_result_from_coefficients(
        prepared,
        output_labels=output_labels,
        coefficients=recentered,
        fit_method="ridge",
        ridge_alpha=alphas,
        ridge_standardize_features=standardize,
        reject_unseen_features=True,
        smooth_support_scale=True,
        extra_metrics={
            "ridge_inner_cv_mae": list(inner_cv_mae),
            "ridge_alpha_grid": list(alpha_grid),
            "ridge_bootstrap_recentered": True,
        },
    )


def write_trained_fusion(
    output_dir: Path,
    *,
    program: Any,
    optimizer_index: int,
    constraint_labels: tuple[str, ...],
    fusion_id: str,
    version: str,
    result: TrainingResult,
) -> LoadedFusionArtifact:
    output_dir.mkdir(parents=True, exist_ok=True)
    split_path = output_dir / "split.json"
    split_path.write_text(result.split.model_dump_json(indent=2) + "\n")
    (output_dir / "metrics.json").write_text(json.dumps(result.metrics, indent=2) + "\n")
    signature = step_group_signature(
        program,
        optimizer_index=optimizer_index,
        constraint_labels=constraint_labels,
    )
    manifest = FusionManifest(
        fusion_id=fusion_id,
        version=version,
        reviewed=False,
        optimizer_index=optimizer_index,
        constraint_labels=constraint_labels,
        group_signature=signature,
        group_signature_sha256=signature.sha256,
        model_sha256="0" * 64,
        training_trace_sha256=result.split.trace_sha256,
        split_manifest_sha256=file_sha256(split_path),
        final_validation_required=True,
        score_only=True,
    )
    return write_unreviewed_fusion_artifact(
        output_dir,
        manifest=manifest,
        model=result.model,
    )
