"""Frozen external audit for the CUSTOM sampled-window MFE bundle."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from proto_language.core import Sequence

from protofuse.phillip.custom_constraints import (
    CustomMetricConfig,
    custom_mfe_constraint,
)
from protofuse.sai.artifacts import file_sha256
from protofuse.sai.exact_custom import (
    FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
    FROZEN_CUSTOM_MFE_SLOPE,
    FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
    SampledCustomMfeEvaluator,
)
from protofuse.sai.signatures import callable_signature, stable_data
from protofuse.sai.training import _rank_correlations, _read_trace


def audit_sampled_custom_mfe(
    trace_paths: tuple[Path, ...],
    *,
    development_trace_sha256: tuple[str, ...],
    development_groups: tuple[str, ...],
    uncertainty_threshold: float,
    workers: int = 8,
    max_normalized_mae: float = 0.05,
    min_spearman: float = 0.90,
    min_coverage: float = 0.30,
    min_groups: int = 4,
    expected_rows_per_trace: int = 1000,
) -> dict[str, Any]:
    """Audit the frozen stride-8 approximation without refitting any parameter."""

    if len(trace_paths) < 1:
        raise ValueError("sampled CUSTOM MFE audit requires held-out traces")
    if (
        isinstance(uncertainty_threshold, bool)
        or not math.isfinite(uncertainty_threshold)
        or uncertainty_threshold < 0.0
    ):
        raise ValueError("sampled CUSTOM MFE audit requires a finite uncertainty threshold")
    if isinstance(expected_rows_per_trace, bool) or expected_rows_per_trace < 1:
        raise ValueError("expected_rows_per_trace must be positive")
    resolved = tuple(path.resolve() for path in trace_paths)
    heldout_hashes = tuple(file_sha256(path) for path in resolved)
    if len(set(heldout_hashes)) != len(heldout_hashes):
        raise ValueError("sampled CUSTOM MFE audit received duplicate trace content")
    overlap = sorted(set(heldout_hashes) & set(development_trace_sha256))
    if overlap:
        raise ValueError(f"held-out trace hash overlaps development data: {overlap}")

    expected_identity = callable_signature(custom_mfe_constraint)
    if expected_identity is None:
        raise RuntimeError("CUSTOM MFE constraint has no callable signature")
    expected_config = stable_data(CustomMetricConfig())
    sequences: list[str] = []
    actual_raw: list[float] = []
    heldout_groups: set[str] = set()
    per_trace_counts: dict[str, int] = {}
    for path in resolved:
        rows = [
            row
            for row in _read_trace(path)
            if row.optimizer_index == 0 and row.constraint_label == "custom_mfe"
        ]
        if len(rows) != expected_rows_per_trace:
            raise ValueError(
                f"{path} has {len(rows)} CUSTOM MFE rows; "
                f"expected {expected_rows_per_trace}"
            )
        trace_groups = {row.group_id for row in rows}
        if len(trace_groups) != 1:
            raise ValueError(f"{path} must contain exactly one held-out group")
        duplicate_groups = sorted(heldout_groups & trace_groups)
        if duplicate_groups:
            raise ValueError(
                f"held-out group appears in more than one trace: {duplicate_groups}"
            )
        heldout_groups.update(trace_groups)
        per_trace_counts[str(path)] = len(rows)
        proposal_indexes = {row.proposal_index for row in rows}
        if proposal_indexes != set(range(expected_rows_per_trace)):
            raise ValueError(
                f"{path} does not contain proposals 0.."
                f"{expected_rows_per_trace - 1} exactly once"
            )
        for row in rows:
            raw = row.metadata.get("mfe_kcal_mol") if isinstance(row.metadata, dict) else None
            if (
                row.error is not None
                or row.score is None
                or row.input_sequences is None
                or len(row.input_sequences) != 1
                or row.tier != "full"
                or row.constraint_identity != expected_identity.identity
                or row.constraint_config != expected_config
                or row.constraint_threshold is not None
                or row.constraint_weight != 1.0
                or isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(float(raw))
            ):
                raise ValueError(f"{path} contains an incompatible CUSTOM MFE row")
            sequences.append(row.input_sequences[0])
            actual_raw.append(float(raw))

    group_overlap = sorted(heldout_groups & set(development_groups))
    if group_overlap:
        raise ValueError(f"held-out groups overlap development groups: {group_overlap}")

    config = CustomMetricConfig()
    evaluator = SampledCustomMfeEvaluator(
        custom_mfe_constraint,
        config,
        workers,
        window_stride=FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
        intercept=FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
        slope=FROZEN_CUSTOM_MFE_SLOPE,
        uncertainty_threshold=uncertainty_threshold,
    )
    inputs: list[tuple[Sequence, ...]] = [
        (Sequence(sequence=sequence, sequence_type="dna"),)
        for sequence in sequences
    ]
    outputs = evaluator.evaluate(inputs, config)
    if len(outputs) != len(inputs):
        raise RuntimeError("sampled CUSTOM MFE audit returned incomplete routed outputs")

    predicted_raw = np.full(len(outputs), np.nan, dtype=np.float64)
    accepted_mask = np.zeros(len(outputs), dtype=np.bool_)
    for index, output in enumerate(outputs):
        metadata = output.metadata
        if not isinstance(metadata, dict):
            raise RuntimeError("sampled CUSTOM MFE audit output metadata is invalid")
        route = metadata.get("protofuse_route")
        if route == "full_model":
            continue
        if route != "surrogate":
            raise RuntimeError("sampled CUSTOM MFE audit output has an invalid route")
        raw = metadata.get("mfe_kcal_mol")
        uncertainty = metadata.get("protofuse_sampled_uncertainty_kcal_mol")
        if (
            isinstance(raw, bool)
            or not isinstance(raw, (int, float))
            or not math.isfinite(float(raw))
            or isinstance(uncertainty, bool)
            or not isinstance(uncertainty, (int, float))
            or not math.isfinite(float(uncertainty))
            or float(uncertainty) > uncertainty_threshold
        ):
            raise RuntimeError(
                "sampled CUSTOM MFE surrogate route bypassed its finite uncertainty gate"
            )
        predicted_raw[index] = float(raw)
        accepted_mask[index] = True

    actual = np.asarray(actual_raw, dtype=np.float64)
    accepted = int(accepted_mask.sum())
    parent_fallback = len(actual) - accepted
    if (
        evaluator.routing_counts["surrogate"] != accepted
        or evaluator.routing_counts["full_model"] != parent_fallback
    ):
        raise RuntimeError("sampled CUSTOM MFE routing counts disagree with routed outputs")
    coverage = accepted / len(actual)
    q05: float | None = None
    q95: float | None = None
    span: float | None = None
    mae: float | None = None
    normalized_mae: float | None = None
    spearman: float | None = None
    if accepted:
        accepted_actual = actual[accepted_mask]
        accepted_predicted = predicted_raw[accepted_mask]
        q05_value, q95_value = np.quantile(accepted_actual, (0.05, 0.95))
        q05 = float(q05_value)
        q95 = float(q95_value)
        span = q95 - q05
        mae = float(np.abs(accepted_actual - accepted_predicted).mean())
        normalized_mae = mae / span if span > 0.0 else None
        spearman = _rank_correlations(
            accepted_actual[:, None],
            accepted_predicted[:, None],
        )[0]

    checks = {
        "accepted_samples": accepted > 0,
        "informative_range": span is not None and span > 0.0,
        "accepted_normalized_mae": (
            normalized_mae is not None and normalized_mae <= max_normalized_mae
        ),
        "accepted_spearman": spearman is not None and spearman >= min_spearman,
        "coverage": accepted > 0 and coverage >= min_coverage,
        "heldout_group_count": len(heldout_groups) >= min_groups,
    }
    passed = all(checks.values())
    return {
        "schema_version": "1.0",
        "status": "pass" if passed else "fail",
        "passed": passed,
        "frozen_spec": {
            "target": "custom_mfe",
            "window_stride": FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
            "windows_per_sequence": 80,
            "full_windows_per_sequence": 638,
            "calibration_intercept_kcal_mol": FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
            "calibration_slope": FROZEN_CUSTOM_MFE_SLOPE,
            "uncertainty_threshold_kcal_mol": uncertainty_threshold,
            "workers": evaluator.workers,
        },
        "provenance": {
            "development_trace_sha256": list(development_trace_sha256),
            "heldout_traces": [
                {"path": str(path), "sha256": digest, "mfe_rows": per_trace_counts[str(path)]}
                for path, digest in zip(resolved, heldout_hashes, strict=True)
            ],
            "development_groups": sorted(development_groups),
            "heldout_groups": sorted(heldout_groups),
            "heldout_group_count": len(heldout_groups),
            "expected_rows_per_trace": expected_rows_per_trace,
            "trace_hash_disjoint": True,
            "group_disjoint": True,
        },
        "samples": {
            "total": len(actual),
            "accepted": accepted,
            "parent_fallback": parent_fallback,
            "coverage": coverage,
            "routing_reasons": dict(sorted(evaluator.routing_reasons.items())),
        },
        "metrics": {
            "q05_kcal_mol": q05,
            "q95_kcal_mol": q95,
            "q95_q05_kcal_mol": span,
            "accepted_mae_kcal_mol": mae,
            "accepted_mae_q95_q05_fraction": normalized_mae,
            "accepted_spearman": spearman,
        },
        "thresholds": {
            "max_accepted_mae_q95_q05_fraction": max_normalized_mae,
            "min_accepted_spearman": min_spearman,
            "min_coverage": min_coverage,
            "min_heldout_groups": min_groups,
            "max_sampled_uncertainty_kcal_mol": uncertainty_threshold,
        },
        "checks": checks,
        "timing": dict(evaluator.timing_seconds),
    }
