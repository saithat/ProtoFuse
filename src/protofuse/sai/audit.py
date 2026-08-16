"""External held-out audit for a frozen linear fusion artifact."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from protofuse.sai.artifacts import file_sha256, load_fusion_artifact
from protofuse.sai.model import LinearEnsemblePredictor
from protofuse.sai.training import (
    SplitManifest,
    _q95_q05_ranges,
    _rank_correlations,
    _read_trace,
    load_teacher_samples,
)
from protofuse.sai.transform import linear_gate_decision


def _labeled(
    labels: tuple[str, ...],
    values: list[float | None] | np.ndarray,
) -> dict[str, float | None]:
    return {
        label: None if value is None else float(value)
        for label, value in zip(labels, values, strict=True)
    }


def audit_frozen_fusion(
    artifact_dir: Path,
    trace_paths: tuple[Path, ...],
    *,
    max_normalized_mae: float = 0.05,
    min_spearman: float = 0.90,
    min_coverage: float = 0.30,
    min_groups: int = 4,
    require_reviewed: bool = True,
) -> dict[str, Any]:
    """Audit a frozen model on external parent traces with leakage checks."""

    if not trace_paths:
        raise ValueError("fusion audit requires at least one held-out trace")
    if max_normalized_mae < 0.0:
        raise ValueError("max_normalized_mae must be non-negative")
    if not -1.0 <= min_spearman <= 1.0:
        raise ValueError("min_spearman must be in [-1, 1]")
    if not 0.0 <= min_coverage <= 1.0:
        raise ValueError("min_coverage must be in [0, 1]")
    if min_groups < 1:
        raise ValueError("min_groups must be at least 1")

    artifact = load_fusion_artifact(artifact_dir, require_reviewed=require_reviewed)
    split_path = artifact.root / "split.json"
    expected_split_hash = artifact.manifest.split_manifest_sha256
    if expected_split_hash is None:
        raise ValueError("fusion artifact has no frozen split manifest hash")
    if split_path.is_symlink() or not split_path.is_file():
        raise ValueError("fusion artifact split.json is missing or unsafe")
    actual_split_hash = file_sha256(split_path)
    if actual_split_hash != expected_split_hash:
        raise ValueError("fusion split manifest hash mismatch")
    split = SplitManifest.model_validate_json(split_path.read_text())
    if split.trace_sha256 != artifact.manifest.training_trace_sha256:
        raise ValueError("fusion manifest and split disagree on training trace hashes")

    resolved_traces = tuple(path.resolve() for path in trace_paths)
    heldout_hashes = tuple(file_sha256(path) for path in resolved_traces)
    if len(set(heldout_hashes)) != len(heldout_hashes):
        raise ValueError("fusion audit received duplicate held-out trace content")
    training_hashes = set(split.trace_sha256) | set(artifact.manifest.training_trace_sha256)
    trace_overlap = sorted(set(heldout_hashes) & training_hashes)
    if trace_overlap:
        raise ValueError(f"held-out trace hash overlaps training data: {trace_overlap}")

    labels = artifact.manifest.constraint_labels
    trace_rows = [row for path in resolved_traces for row in _read_trace(path)]
    expected_constraints = {
        constraint.label: constraint
        for constraint in artifact.manifest.group_signature.constraints
    }
    relevant_rows = [
        row
        for row in trace_rows
        if row.optimizer_index == artifact.manifest.optimizer_index
        and row.constraint_label in labels
    ]
    if not relevant_rows:
        raise ValueError("held-out traces contain no rows for the frozen constraint group")
    for row in relevant_rows:
        expected = expected_constraints[row.constraint_label]
        expected_identity = expected.function.identity if expected.function is not None else None
        if (
            row.error is not None
            or row.score is None
            or row.input_sequences is None
            or row.has_structures
            or row.has_logits
        ):
            raise ValueError("held-out traces contain failed or incomplete target rows")
        if (
            row.constraint_identity != expected_identity
            or row.constraint_config != expected.function_config
            or row.constraint_threshold != expected.threshold
            or row.constraint_weight != expected.weight
        ):
            raise ValueError(
                f"held-out trace contract differs for constraint {row.constraint_label!r}"
            )

    heldout_groups = {row.group_id for row in relevant_rows}
    split_groups = {
        *split.train_groups,
        *split.calibration_groups,
        *split.audit_groups,
    }
    group_overlap = sorted(heldout_groups & split_groups)
    if group_overlap:
        raise ValueError(f"held-out groups overlap frozen split groups: {group_overlap}")

    samples = load_teacher_samples(
        resolved_traces,
        optimizer_index=artifact.manifest.optimizer_index,
        constraint_labels=labels,
    )
    if len(relevant_rows) != len(samples) * len(labels):
        raise ValueError("held-out traces have incomplete or unequal objective occurrences")
    actual = np.asarray([sample.outputs for sample in samples], dtype=np.float64)
    if not np.all(np.isfinite(actual)) or np.any((actual < 0.0) | (actual > 1.0)):
        raise ValueError("held-out parent scores must be finite and in [0, 1]")

    predictor = LinearEnsemblePredictor(artifact.model)
    predictions = [predictor.predict(sample.sequences) for sample in samples]
    predicted = np.asarray([prediction.values for prediction in predictions], dtype=np.float64)
    decisions = [
        linear_gate_decision(
            artifact.model,
            values=prediction.values,
            uncertainties=prediction.uncertainties,
            support_score=prediction.support_score,
        )
        for prediction in predictions
    ]
    accepted = np.asarray(
        [decision.use_surrogate for decision in decisions],
        dtype=np.bool_,
    )
    routing_reasons = Counter(decision.reason for decision in decisions)

    q05 = np.quantile(actual, 0.05, axis=0)
    q95 = np.quantile(actual, 0.95, axis=0)
    ranges = _q95_q05_ranges(actual)
    range_checks = {
        label: math.isfinite(float(span)) and float(span) > 0.0
        for label, span in zip(labels, ranges, strict=True)
    }

    finite_prediction_columns = np.all(np.isfinite(predicted), axis=0)
    all_mae: list[float | None] = [
        float(np.abs(actual[:, index] - predicted[:, index]).mean())
        if finite_prediction_columns[index]
        else None
        for index in range(len(labels))
    ]
    all_spearman = [
        value if finite_prediction_columns[index] else None
        for index, value in enumerate(_rank_correlations(actual, predicted))
    ]
    accepted_count = int(accepted.sum())
    coverage = float(accepted.mean())
    if accepted_count:
        accepted_actual = actual[accepted]
        accepted_predicted = predicted[accepted]
        accepted_mae_array = np.abs(accepted_actual - accepted_predicted).mean(axis=0)
        accepted_mae_values: list[float | None] = list(accepted_mae_array)
        normalized_mae = [
            float(error / span)
            if math.isfinite(float(span)) and float(span) > 0.0
            else None
            for error, span in zip(accepted_mae_array, ranges, strict=True)
        ]
        accepted_spearman = _rank_correlations(accepted_actual, accepted_predicted)
    else:
        accepted_mae_values = [None] * len(labels)
        normalized_mae = [None] * len(labels)
        accepted_spearman = [None] * len(labels)

    normalized_checks = {
        label: value is not None and value <= max_normalized_mae
        for label, value in zip(labels, normalized_mae, strict=True)
    }
    spearman_checks = {
        label: value is not None and value >= min_spearman
        for label, value in zip(labels, accepted_spearman, strict=True)
    }
    coverage_passed = accepted_count > 0 and coverage >= min_coverage
    group_count_passed = len(heldout_groups) >= min_groups
    passed = (
        all(range_checks.values())
        and all(normalized_checks.values())
        and all(spearman_checks.values())
        and coverage_passed
        and group_count_passed
    )

    return {
        "schema_version": "1.0",
        "status": "pass" if passed else "fail",
        "passed": passed,
        "artifact": {
            "fusion_id": artifact.manifest.fusion_id,
            "version": artifact.manifest.version,
            "manifest_sha256": file_sha256(artifact.root / "manifest.json"),
            "model_sha256": artifact.manifest.model_sha256,
            "split_sha256": actual_split_hash,
        },
        "labels": list(labels),
        "provenance": {
            "training_trace_sha256": list(split.trace_sha256),
            "heldout_traces": [
                {"path": str(path), "sha256": digest}
                for path, digest in zip(resolved_traces, heldout_hashes, strict=True)
            ],
            "split_groups": {
                "train": list(split.train_groups),
                "calibration": list(split.calibration_groups),
                "audit": list(split.audit_groups),
            },
            "heldout_groups": sorted(heldout_groups),
            "heldout_group_count": len(heldout_groups),
            "trace_hash_disjoint": True,
            "group_disjoint": True,
        },
        "samples": {
            "total": len(samples),
            "accepted": accepted_count,
            "rejected": len(samples) - accepted_count,
            "coverage": coverage,
            "routing_reasons": dict(sorted(routing_reasons.items())),
        },
        "metrics": {
            "q05": _labeled(labels, q05),
            "q95": _labeled(labels, q95),
            "q95_q05_range": _labeled(labels, ranges),
            "all_mae": _labeled(labels, all_mae),
            "accepted_mae": _labeled(labels, accepted_mae_values),
            "accepted_mae_q95_q05_fraction": _labeled(labels, normalized_mae),
            "all_spearman": _labeled(labels, all_spearman),
            "accepted_spearman": _labeled(labels, accepted_spearman),
        },
        "thresholds": {
            "max_accepted_mae_q95_q05_fraction": max_normalized_mae,
            "min_accepted_spearman": min_spearman,
            "min_coverage": min_coverage,
            "min_heldout_groups": min_groups,
        },
        "checks": {
            "informative_objective_ranges": {
                "passed": all(range_checks.values()),
                "per_objective": range_checks,
            },
            "accepted_normalized_mae": {
                "passed": all(normalized_checks.values()),
                "per_objective": normalized_checks,
            },
            "accepted_spearman": {
                "passed": all(spearman_checks.values()),
                "per_objective": spearman_checks,
            },
            "coverage": {
                "passed": coverage_passed,
                "accepted_samples_required": True,
            },
            "heldout_group_count": {
                "passed": group_count_passed,
                "actual": len(heldout_groups),
                "required": min_groups,
            },
        },
    }
