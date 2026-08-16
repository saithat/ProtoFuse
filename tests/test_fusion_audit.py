from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from proto_language.core import Constraint, ConstraintOutput, Construct, Program, Segment
from proto_language.optimizer import RejectionSamplingOptimizer, RejectionSamplingOptimizerConfig

from protofuse.sai.artifacts import FusionManifest, file_sha256, write_unreviewed_fusion_artifact
from protofuse.sai.audit import audit_frozen_fusion
from protofuse.sai.model import LinearEnsembleModel, SequenceFeatureSchema
from protofuse.sai.signatures import step_group_signature
from protofuse.sai.tracing import TraceRow
from protofuse.sai.training import SplitManifest

LABELS = ("fraction_a", "fraction_c")
SEQUENCES = ("AAAA", "AAAC", "AACC", "ACCC", "CCCC")


def _objective(
    inputs: list[tuple[Any, ...]],
    config: dict[str, Any] | None,
) -> list[ConstraintOutput]:
    del config
    return [ConstraintOutput(score=0.0) for _ in inputs]


OBJECTIVE_IDENTITY = f"{_objective.__module__}.{_objective.__qualname__}"


def _program() -> Program:
    segment = Segment(sequence="AACC", sequence_type="dna", label="target")
    optimizer = RejectionSamplingOptimizer(
        constructs=[Construct([segment])],
        generators=[],
        constraints=[
            Constraint(
                inputs=[segment],
                function=_objective,
                function_config={},
                label=label,
            )
            for label in LABELS
        ],
        config=RejectionSamplingOptimizerConfig(
            num_samples=1,
            num_results=1,
            proposal_source="existing_results",
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def _model(
    *,
    support_threshold: float = 10.0,
    feature_center: tuple[float, float] = (0.5, 0.5),
) -> LinearEnsembleModel:
    matrix = (
        (0.0, 0.0),
        (1.0, 0.0),
        (0.0, 1.0),
    )
    return LinearEnsembleModel(
        input_schemas=(
            SequenceFeatureSchema(
                sequence_type="dna",
                alphabet="AC",
                kmer_size=1,
                include_composition=False,
                expected_length=4,
            ),
        ),
        output_labels=LABELS,
        coefficients=(matrix, matrix),
        feature_center=feature_center,
        feature_scale=(1.0, 1.0),
        support_threshold=support_threshold,
        uncertainty_threshold=0.0,
        calibration_absolute_error=(0.0, 0.0),
    )


def _write_artifact(
    root: Path,
    *,
    training_hash: str = "a" * 64,
    audit_group: str = "internal-audit",
    support_threshold: float = 10.0,
    feature_center: tuple[float, float] = (0.5, 0.5),
) -> Path:
    split = SplitManifest(
        seed=0,
        trace_sha256=(training_hash,),
        train_groups=("train",),
        calibration_groups=("calibration",),
        audit_groups=(audit_group,),
        train_samples=1,
        calibration_samples=1,
        audit_samples=1,
    )
    root.mkdir(parents=True)
    split_path = root / "split.json"
    split_path.write_text(split.model_dump_json(indent=2) + "\n")
    signature = step_group_signature(
        _program(),
        optimizer_index=0,
        constraint_labels=LABELS,
    )
    manifest = FusionManifest(
        fusion_id="audit-fixture",
        version="1",
        optimizer_index=0,
        constraint_labels=LABELS,
        group_signature=signature,
        group_signature_sha256=signature.sha256,
        model_sha256="0" * 64,
        training_trace_sha256=(training_hash,),
        split_manifest_sha256=file_sha256(split_path),
    )
    write_unreviewed_fusion_artifact(
        root,
        manifest=manifest,
        model=_model(
            support_threshold=support_threshold,
            feature_center=feature_center,
        ),
    )
    return root


def _write_trace(
    path: Path,
    *,
    group_id: str = "external",
    constant_second_output: bool = False,
) -> Path:
    rows: list[TraceRow] = []
    for sample_index, sequence in enumerate(SEQUENCES):
        fractions = (sequence.count("A") / 4.0, sequence.count("C") / 4.0)
        if constant_second_output:
            fractions = (fractions[0], 0.5)
        for label, score in zip(LABELS, fractions, strict=True):
            rows.append(
                TraceRow(
                    recorded_at="2026-08-16T00:00:00+00:00",
                    run_id="heldout",
                    group_id=group_id,
                    program_sha256="0" * 64,
                    optimizer_index=0,
                    constraint_label=label,
                    constraint_identity=OBJECTIVE_IDENTITY,
                    constraint_config={},
                    constraint_threshold=None,
                    constraint_weight=1.0,
                    call_index=sample_index,
                    proposal_index=0,
                    input_sha256=(sha256(sequence.encode()).hexdigest(),),
                    input_sequences=(sequence,),
                    input_structure_sha256=(None,),
                    score=score,
                    metadata={},
                    has_structures=False,
                    has_logits=False,
                    call_latency_seconds=0.0,
                )
            )
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows))
    return path


def test_frozen_audit_reports_external_selective_metrics(tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path / "artifact")
    trace = _write_trace(tmp_path / "heldout.jsonl")

    report = audit_frozen_fusion(
        artifact,
        (trace,),
        min_groups=1,
        require_reviewed=False,
    )

    assert report["status"] == "pass"
    assert report["labels"] == list(LABELS)
    assert report["provenance"]["trace_hash_disjoint"] is True
    assert report["provenance"]["group_disjoint"] is True
    assert report["samples"] == {
        "total": 5,
        "accepted": 5,
        "rejected": 0,
        "coverage": 1.0,
        "routing_reasons": {"calibrated_in_domain": 5},
    }
    assert report["metrics"]["all_mae"] == pytest.approx(
        {label: 0.0 for label in LABELS}
    )
    assert report["metrics"]["accepted_mae_q95_q05_fraction"] == pytest.approx(
        {label: 0.0 for label in LABELS}
    )
    assert report["metrics"]["all_spearman"] == pytest.approx(
        {label: 1.0 for label in LABELS}
    )
    assert report["metrics"]["accepted_spearman"] == pytest.approx(
        {label: 1.0 for label in LABELS}
    )
    assert all(check["passed"] for check in report["checks"].values())


@pytest.mark.parametrize("leakage", ["hash", "group"])
def test_frozen_audit_rejects_training_leakage(tmp_path: Path, leakage: str) -> None:
    trace = _write_trace(tmp_path / "heldout.jsonl")
    artifact = _write_artifact(
        tmp_path / "artifact",
        training_hash=file_sha256(trace) if leakage == "hash" else "a" * 64,
        audit_group="external" if leakage == "group" else "internal-audit",
    )

    with pytest.raises(ValueError, match="overlap"):
        audit_frozen_fusion(artifact, (trace,), require_reviewed=False)


def test_frozen_audit_rejects_zero_range_objective(tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path / "artifact")
    trace = _write_trace(tmp_path / "constant.jsonl", constant_second_output=True)

    report = audit_frozen_fusion(
        artifact,
        (trace,),
        min_groups=1,
        require_reviewed=False,
    )

    assert report["status"] == "fail"
    assert report["metrics"]["accepted_mae_q95_q05_fraction"]["fraction_c"] is None
    assert report["checks"]["informative_objective_ranges"] == {
        "passed": False,
        "per_objective": {"fraction_a": True, "fraction_c": False},
    }


def test_frozen_audit_rejects_incomplete_objective_rows(tmp_path: Path) -> None:
    artifact = _write_artifact(tmp_path / "artifact")
    trace = _write_trace(tmp_path / "incomplete.jsonl")
    rows = trace.read_text().splitlines()
    trace.write_text("\n".join(rows[:-1]) + "\n")

    with pytest.raises(ValueError, match="incomplete or unequal"):
        audit_frozen_fusion(artifact, (trace,), require_reviewed=False)


def test_frozen_audit_preserves_zero_accepted_as_failure(tmp_path: Path) -> None:
    artifact = _write_artifact(
        tmp_path / "artifact",
        support_threshold=0.0,
        feature_center=(0.51, 0.49),
    )
    trace = _write_trace(tmp_path / "heldout.jsonl")

    report = audit_frozen_fusion(
        artifact,
        (trace,),
        min_groups=1,
        require_reviewed=False,
    )

    assert report["status"] == "fail"
    assert report["samples"]["accepted"] == 0
    assert report["metrics"]["accepted_mae"] == {
        "fraction_a": None,
        "fraction_c": None,
    }
    assert report["metrics"]["accepted_spearman"] == {
        "fraction_a": None,
        "fraction_c": None,
    }
    assert report["checks"]["accepted_spearman"]["passed"] is False


def test_frozen_audit_requires_four_independent_groups_by_default(
    tmp_path: Path,
) -> None:
    artifact = _write_artifact(tmp_path / "artifact")
    trace = _write_trace(tmp_path / "heldout.jsonl")

    report = audit_frozen_fusion(artifact, (trace,), require_reviewed=False)

    assert report["status"] == "fail"
    assert report["provenance"]["heldout_group_count"] == 1
    assert report["checks"]["heldout_group_count"] == {
        "passed": False,
        "actual": 1,
        "required": 4,
    }


def test_fusion_audit_cli_writes_failure_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse import cli
    from protofuse.sai import audit

    output = tmp_path / "audit.json"
    captured: dict[str, Any] = {}

    def fake_audit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "fail", "passed": False}

    monkeypatch.setattr(audit, "audit_frozen_fusion", fake_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "protofuse",
            "fusion",
            "audit",
            str(tmp_path / "artifact"),
            "--trace",
            str(tmp_path / "heldout.jsonl"),
            "--out",
            str(output),
            "--allow-unreviewed",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        cli.main()

    assert raised.value.code == 1
    assert json.loads(output.read_text()) == {"status": "fail", "passed": False}
    assert captured == {
        "max_normalized_mae": 0.05,
        "min_spearman": 0.90,
        "min_coverage": 0.30,
        "min_groups": 4,
        "require_reviewed": False,
    }
    assert not (output.parent / f".{output.name}.tmp").exists()
