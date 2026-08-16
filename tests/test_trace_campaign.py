from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from protofuse.sai.artifacts import file_sha256
from protofuse.sai.trace_campaign import (
    ArtifactFreeze,
    TraceCampaignPlan,
    TraceCohort,
    clean_trace,
    load_plan,
    load_verified_artifact_freeze,
    plan_sha256,
    write_plan,
)
from protofuse.sai.tracing import TraceRow

LABELS = ("protein_length", "mpnn_probability", "structure_plddt")
NATIVE = "A" * 8


def _plan() -> TraceCampaignPlan:
    return TraceCampaignPlan(
        campaign_id="test",
        collection_dir="collection",
        collection_id="collection",
        collection_manifest_sha256="c" * 64,
        program_id="design-001",
        methodology_id="method",
        program_sha256="p" * 64,
        optimizer_index=0,
        trace_labels=LABELS,
        teacher_labels=("mpnn_probability", "structure_plddt"),
        native_input_sha256=sha256(NATIVE.encode()).hexdigest(),
        expected_calls_per_label=3,
        expected_rows=9,
        modal_gpu="H100:1",
        split_seed=42,
        cohorts=(
            TraceCohort(name="development", seeds=(1, 2, 3, 4, 5)),
            TraceCohort(name="external", seeds=(10, 11, 12, 13)),
        ),
    )


def _row(label: str, sequence: str, call_index: int) -> TraceRow:
    return TraceRow(
        schema_version="1.1",
        constraint_config_scope="pre_run_contract",
        recorded_at="2026-08-16T00:00:00+00:00",
        run_id="v3-dev-1",
        group_id="v3-dev-1",
        collection_id="collection",
        program_id="design-001",
        methodology_id="method",
        tier="smoke",
        program_seed=1,
        program_sha256="p" * 64,
        optimizer_index=0,
        constraint_label=label,
        constraint_identity=f"test.{label}",
        constraint_config={},
        constraint_threshold=None,
        constraint_weight=1.0,
        call_index=call_index,
        proposal_index=0,
        input_sha256=(sha256(sequence.encode()).hexdigest(),),
        input_sequences=(sequence,),
        input_structure_sha256=(None,),
        score=0.1,
        metadata={},
        has_structures=False,
        has_logits=False,
        call_latency_seconds=0.1,
        error=None,
    )


def _write_trace(path: Path, sequences: tuple[str, ...]) -> None:
    rows = [
        _row(label, sequence, index * len(LABELS) + offset)
        for index, sequence in enumerate(sequences)
        for offset, label in enumerate(LABELS)
    ]
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows))


def test_plan_is_immutable(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    plan = _plan()
    write_plan(path, plan)
    write_plan(path, plan)
    assert load_plan(path) == plan
    with pytest.raises(ValueError, match="different frozen inputs"):
        write_plan(path, plan.model_copy(update={"split_seed": 7}))


def test_plan_rejects_inconsistent_cohorts_and_labels() -> None:
    with pytest.raises(ValueError, match="duplicate seeds"):
        TraceCohort(name="development", seeds=(1, 1))

    values = _plan().model_dump(mode="python")
    values["cohorts"] = (
        TraceCohort(name="development", seeds=(1, 2, 3, 4, 5)),
        TraceCohort(name="external", seeds=(5, 10, 11, 12)),
    )
    with pytest.raises(ValueError, match="seeds overlap"):
        TraceCampaignPlan.model_validate(values)

    values = _plan().model_dump(mode="python")
    values["teacher_labels"] = ("mpnn_probability", "not_traced")
    with pytest.raises(ValueError, match="subset"):
        TraceCampaignPlan.model_validate(values)

    values = _plan().model_dump(mode="python")
    values["expected_rows"] = 8
    with pytest.raises(ValueError, match="calls per label"):
        TraceCampaignPlan.model_validate(values)


def test_artifact_freeze_detects_post_lock_changes(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    for name in ("manifest.json", "model.json", "split.json"):
        artifact.joinpath(name).write_text(f"{name}\n")
    plan = _plan()
    freeze = ArtifactFreeze(
        artifact=str(artifact),
        files={
            name: file_sha256(artifact / name)
            for name in ("manifest.json", "model.json", "split.json")
        },
        frozen_at="2026-08-16T00:00:00+00:00",
        plan_sha256=plan_sha256(plan),
    )
    path = tmp_path / "artifact-freeze.json"
    path.write_text(freeze.model_dump_json())
    assert load_verified_artifact_freeze(path, plan=plan) == freeze

    artifact.joinpath("model.json").write_text("changed\n")
    with pytest.raises(ValueError, match="changed after external-test lock"):
        load_verified_artifact_freeze(path, plan=plan)


def test_clean_trace_removes_native_and_duplicate_inputs(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    clean = tmp_path / "clean.jsonl"
    first = "C" + NATIVE[1:]
    second = "D" + NATIVE[1:]
    _write_trace(raw, (NATIVE, first, second))
    seen = {sha256(first.encode()).hexdigest()}
    result = clean_trace(
        raw,
        clean,
        plan=_plan(),
        seed=1,
        run_id="v3-dev-1",
        group_id="v3-dev-1",
        already_seen_inputs=seen,
    )
    assert result.raw_rows == 9
    assert result.clean_rows == 3
    assert result.teacher_samples == 1
    assert result.duplicate_samples_removed == 1
    assert NATIVE not in clean.read_text()
    assert second in clean.read_text()


def test_clean_trace_removes_later_return_to_native(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    clean = tmp_path / "clean.jsonl"
    first = "C" + NATIVE[1:]
    _write_trace(raw, (NATIVE, first, NATIVE))
    result = clean_trace(
        raw,
        clean,
        plan=_plan(),
        seed=1,
        run_id="v3-dev-1",
        group_id="v3-dev-1",
        already_seen_inputs=set(),
    )
    assert result.teacher_samples == 1
    assert result.duplicate_samples_removed == 1
    assert clean.read_text().count(first) == len(LABELS)


def test_clean_trace_rejects_partial_or_legacy_rows(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    clean = tmp_path / "clean.jsonl"
    _write_trace(raw, (NATIVE, "C" + NATIVE[1:], "D" + NATIVE[1:]))
    raw.write_text("\n".join(raw.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(ValueError, match="expected exactly 9"):
        clean_trace(
            raw,
            clean,
            plan=_plan(),
            seed=1,
            run_id="v3-dev-1",
            group_id="v3-dev-1",
            already_seen_inputs=set(),
        )
