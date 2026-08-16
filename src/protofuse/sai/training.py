"""Reproducible grouped training for the first portable fusion baseline."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from protofuse.sai.artifacts import (
    FusionManifest,
    LoadedFusionArtifact,
    file_sha256,
    write_unreviewed_fusion_artifact,
)
from protofuse.sai.model import LinearEnsembleModel, SequenceFeatureSchema, featurize_inputs
from protofuse.sai.signatures import step_group_signature
from protofuse.sai.tracing import TraceRow


@dataclass(frozen=True)
class TeacherSample:
    sequences: tuple[str, ...]
    outputs: tuple[float, ...]
    group_id: str


class SplitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    seed: int
    trace_sha256: tuple[str, ...]
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


def load_teacher_samples(
    trace_paths: tuple[Path, ...],
    *,
    optimizer_index: int,
    constraint_labels: tuple[str, ...],
) -> tuple[TeacherSample, ...]:
    """Join objective rows by group and input, preserving repeated occurrences."""

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
                continue
            if row.has_structures or row.has_logits:
                raise ValueError(
                    "score-only training cannot replace structure/logit-producing outputs"
                )
            key = (row.run_id, row.group_id, row.optimizer_index, row.input_sha256)
            buckets[key][row.constraint_label].append(row)

    samples: list[TeacherSample] = []
    for key in sorted(buckets):
        per_label = buckets[key]
        if any(label not in per_label for label in constraint_labels):
            continue
        occurrences = min(len(per_label[label]) for label in constraint_labels)
        for occurrence in range(occurrences):
            rows = [per_label[label][occurrence] for label in constraint_labels]
            sequences = rows[0].input_sequences
            if sequences is None or any(row.input_sequences != sequences for row in rows):
                raise ValueError("joined teacher objectives disagree on input sequences")
            samples.append(
                TeacherSample(
                    sequences=sequences,
                    outputs=tuple(float(row.score) for row in rows if row.score is not None),
                    group_id=key[1],
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
                include_composition=True,
                expected_length=next(iter(lengths)) if len(lengths) == 1 else None,
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


def _quantile(values: np.ndarray, probability: float) -> float:
    return float(np.quantile(values, probability, method="higher"))


def train_linear_ensemble(
    samples: tuple[TeacherSample, ...],
    *,
    output_labels: tuple[str, ...],
    trace_paths: tuple[Path, ...],
    schemas: tuple[SequenceFeatureSchema, ...] | None = None,
    seed: int = 0,
    ensemble_size: int = 8,
) -> TrainingResult:
    if ensemble_size < 2:
        raise ValueError("ensemble_size must be at least 2")
    if any(len(sample.outputs) != len(output_labels) for sample in samples):
        raise ValueError("teacher output dimensions do not match output labels")
    resolved_schemas = schemas or infer_feature_schemas(samples)
    x = np.asarray(
        [featurize_inputs(sample.sequences, resolved_schemas) for sample in samples],
        dtype=np.float64,
    )
    y = np.asarray([sample.outputs for sample in samples], dtype=np.float64)
    if not np.all(np.isfinite(y)):
        raise ValueError("teacher outputs must be finite")
    if np.any((y < 0.0) | (y > 1.0)):
        raise ValueError("portable score-only training requires teacher outputs in [0, 1]")
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

    design = np.column_stack((np.ones(len(x)), x))
    rng = np.random.default_rng(seed)
    train_group_list = sorted(train_groups)
    coefficients: list[np.ndarray] = []
    for _ in range(ensemble_size):
        sampled_groups = rng.choice(
            train_group_list,
            size=len(train_group_list),
            replace=True,
        )
        indices = np.concatenate(
            [np.flatnonzero(group_values == group) for group in sampled_groups]
        )
        coefficients.append(np.linalg.lstsq(design[indices], y[indices], rcond=None)[0])
    stacked = np.stack([design @ coefficient for coefficient in coefficients])
    prediction = stacked.mean(axis=0)
    uncertainty = stacked.std(axis=0)
    center = x[train_mask].mean(axis=0)
    scale = np.maximum(x[train_mask].std(axis=0), 1e-6)
    support = np.sqrt(np.mean(np.square((x - center) / scale), axis=1))
    support_threshold = _quantile(support[calibration_mask], 0.99)
    uncertainty_threshold = _quantile(
        uncertainty[calibration_mask].max(axis=1),
        0.99,
    )
    calibration_error = np.abs(y[calibration_mask] - prediction[calibration_mask])
    error_quantiles = tuple(
        _quantile(calibration_error[:, output_index], 0.99)
        for output_index in range(len(output_labels))
    )
    model = LinearEnsembleModel(
        input_schemas=resolved_schemas,
        output_labels=output_labels,
        coefficients=tuple(
            tuple(tuple(float(value) for value in row) for row in coefficient)
            for coefficient in coefficients
        ),
        feature_center=tuple(float(value) for value in center),
        feature_scale=tuple(float(value) for value in scale),
        support_threshold=support_threshold,
        uncertainty_threshold=uncertainty_threshold,
        calibration_absolute_error=error_quantiles,
    )
    split = SplitManifest(
        seed=seed,
        trace_sha256=tuple(file_sha256(path) for path in trace_paths),
        train_groups=tuple(sorted(train_groups)),
        calibration_groups=tuple(sorted(calibration_groups)),
        audit_groups=tuple(sorted(audit_groups)),
        train_samples=int(train_mask.sum()),
        calibration_samples=int(calibration_mask.sum()),
        audit_samples=int(audit_mask.sum()),
    )
    audit_error = np.abs(y[audit_mask] - prediction[audit_mask])
    audit_prediction = prediction[audit_mask]
    audit_uncertainty = uncertainty[audit_mask].max(axis=1)
    audit_support = support[audit_mask]
    audit_in_range = np.all(
        np.isfinite(audit_prediction)
        & (audit_prediction >= 0.0)
        & (audit_prediction <= 1.0),
        axis=1,
    )
    audit_accepted = (
        audit_in_range
        & (audit_support <= support_threshold)
        & (audit_uncertainty <= uncertainty_threshold)
    )
    accepted_error = audit_error[audit_accepted]
    metrics = {
        "calibration_mae": calibration_error.mean(axis=0).tolist(),
        "audit_mae": audit_error.mean(axis=0).tolist(),
        "audit_rmse": np.sqrt(np.mean(np.square(audit_error), axis=0)).tolist(),
        "audit_max_error": audit_error.max(axis=0).tolist(),
        "audit_support_coverage": float(np.mean(audit_support <= support_threshold)),
        "audit_uncertainty_coverage": float(np.mean(audit_uncertainty <= uncertainty_threshold)),
        "audit_selective_coverage": float(np.mean(audit_accepted)),
        "audit_accepted_mae": (
            accepted_error.mean(axis=0).tolist() if len(accepted_error) else None
        ),
        "audit_accepted_max_error": (
            accepted_error.max(axis=0).tolist() if len(accepted_error) else None
        ),
    }
    return TrainingResult(model=model, split=split, metrics=metrics)


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
