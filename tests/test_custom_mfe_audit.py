from __future__ import annotations

import math
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from proto_language.core import ConstraintOutput

from protofuse.phillip.custom_constraints import (
    CustomMetricConfig,
    custom_mfe_constraint,
)
from protofuse.sai.custom_mfe_audit import audit_sampled_custom_mfe
from protofuse.sai.exact_custom import SampledCustomMfeEvaluator
from protofuse.sai.signatures import callable_signature, stable_data
from protofuse.sai.tracing import TraceRow

SEQUENCES = ("A" * 717, "C" * 717, "G" * 717)
ACTUAL_RAW = dict(zip(SEQUENCES, (-1.0, -2.0, -3.0), strict=True))


def _write_trace(
    path: Path,
    *,
    group_id: str = "heldout",
    sequences: tuple[str, ...] = SEQUENCES,
) -> Path:
    identity = callable_signature(custom_mfe_constraint)
    assert identity is not None
    rows = []
    for proposal_index, sequence in enumerate(sequences):
        raw = ACTUAL_RAW[sequence]
        rows.append(
            TraceRow(
                recorded_at="2026-08-16T00:00:00+00:00",
                run_id=group_id,
                group_id=group_id,
                collection_id="custom-egfp-lung",
                program_id="design-001",
                methodology_id="custom-egfp-v2",
                tier="full",
                program_seed=40,
                program_sha256="0" * 64,
                optimizer_index=0,
                constraint_label="custom_mfe",
                constraint_identity=identity.identity,
                constraint_config=stable_data(CustomMetricConfig()),
                constraint_threshold=None,
                constraint_weight=1.0,
                call_index=0,
                proposal_index=proposal_index,
                input_sha256=(sha256(sequence.encode()).hexdigest(),),
                input_sequences=(sequence,),
                input_structure_sha256=(None,),
                score=(raw + 200.0) / 200.0,
                metadata={"mfe_kcal_mol": raw},
                has_structures=False,
                has_logits=False,
                call_latency_seconds=0.0,
            )
        )
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows))
    return path


def _patch_evaluator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    predicted: tuple[float, ...],
    uncertainties: tuple[float, ...],
) -> None:
    predicted_by_sequence = dict(zip(SEQUENCES, predicted, strict=True))
    uncertainty_by_sequence = dict(zip(SEQUENCES, uncertainties, strict=True))

    def fake_predictions(
        self: SampledCustomMfeEvaluator,
        input_sequences: list[tuple[Any, ...]],
        config: CustomMetricConfig,
    ) -> tuple[list[float], list[float]]:
        del self, config
        sequences = [inputs[0].sequence for inputs in input_sequences]
        return (
            [predicted_by_sequence[sequence] for sequence in sequences],
            [uncertainty_by_sequence[sequence] for sequence in sequences],
        )

    def fake_parent_outputs(
        self: SampledCustomMfeEvaluator,
        input_sequences: list[tuple[Any, ...]],
    ) -> list[ConstraintOutput]:
        del self
        return [
            ConstraintOutput(
                score=(ACTUAL_RAW[inputs[0].sequence] + 200.0) / 200.0,
                metadata={"mfe_kcal_mol": ACTUAL_RAW[inputs[0].sequence]},
            )
            for inputs in input_sequences
        ]

    monkeypatch.setattr(SampledCustomMfeEvaluator, "_parallel_predictions", fake_predictions)
    monkeypatch.setattr(SampledCustomMfeEvaluator, "_parent_outputs", fake_parent_outputs)


def _audit(trace: Path, **overrides: Any) -> dict[str, Any]:
    options = {
        "development_trace_sha256": (),
        "development_groups": ("development",),
        "uncertainty_threshold": 0.5,
        "workers": 1,
        "max_normalized_mae": 1.0,
        "min_spearman": 0.90,
        "min_coverage": 0.30,
        "min_groups": 1,
        "expected_rows_per_trace": 3,
    }
    options.update(overrides)
    return audit_sampled_custom_mfe((trace,), **options)


def test_sampled_mfe_audit_metrics_use_only_uncertainty_accepted_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = _write_trace(tmp_path / "heldout.jsonl")
    _patch_evaluator(
        monkeypatch,
        predicted=(-1.1, -1.7, -99.0),
        uncertainties=(0.1, 0.2, 0.6),
    )

    report = _audit(trace)

    assert report["status"] == "pass"
    assert report["samples"]["accepted"] == 2
    assert report["samples"]["parent_fallback"] == 1
    assert report["samples"]["coverage"] == pytest.approx(2 / 3)
    assert report["metrics"] == pytest.approx(
        {
            "q05_kcal_mol": -1.95,
            "q95_kcal_mol": -1.05,
            "q95_q05_kcal_mol": 0.90,
            "accepted_mae_kcal_mol": 0.20,
            "accepted_mae_q95_q05_fraction": 2 / 9,
            "accepted_spearman": 1.0,
        }
    )
    assert report["frozen_spec"]["uncertainty_threshold_kcal_mol"] == 0.5


def test_sampled_mfe_audit_zero_accepted_is_structured_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = _write_trace(tmp_path / "heldout.jsonl")
    _patch_evaluator(
        monkeypatch,
        predicted=(-1.1, -1.7, -2.8),
        uncertainties=(0.6, math.inf, math.nan),
    )

    report = _audit(trace)

    assert report["status"] == "fail"
    assert report["samples"]["accepted"] == 0
    assert report["samples"]["parent_fallback"] == 3
    assert report["samples"]["coverage"] == 0.0
    assert all(value is None for value in report["metrics"].values())
    assert report["checks"]["accepted_samples"] is False
    assert report["checks"]["accepted_normalized_mae"] is False
    assert report["checks"]["accepted_spearman"] is False
    assert report["checks"]["coverage"] is False


@pytest.mark.parametrize("threshold", [True, -0.01, math.inf, -math.inf, math.nan])
def test_sampled_mfe_audit_requires_finite_uncertainty_threshold(
    tmp_path: Path,
    threshold: float,
) -> None:
    with pytest.raises(ValueError, match="finite uncertainty threshold"):
        audit_sampled_custom_mfe(
            (tmp_path / "unused.jsonl",),
            development_trace_sha256=(),
            development_groups=(),
            uncertainty_threshold=threshold,
        )


def test_sampled_mfe_audit_rejects_incomplete_trace(tmp_path: Path) -> None:
    trace = _write_trace(tmp_path / "incomplete.jsonl", sequences=SEQUENCES[:2])

    with pytest.raises(ValueError, match="has 2 CUSTOM MFE rows; expected 3"):
        _audit(trace)


def test_sampled_mfe_audit_keeps_minimum_group_count_as_scientific_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = _write_trace(tmp_path / "heldout.jsonl")
    _patch_evaluator(
        monkeypatch,
        predicted=(-1.0, -2.0, -3.0),
        uncertainties=(0.1, 0.1, 0.1),
    )

    report = _audit(trace, min_groups=4)

    assert report["status"] == "fail"
    assert report["provenance"]["heldout_group_count"] == 1
    assert report["checks"]["heldout_group_count"] is False
