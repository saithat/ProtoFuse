#!/usr/bin/env python3
"""Freeze the compact ridge candidate for the v3 joint-model campaign."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from protofuse.sai.analyzer import load_reviewed_program
from protofuse.sai.artifacts import file_sha256
from protofuse.sai.model import (
    SequenceFeatureSchema,
    sequence_fixed_context_sha256,
)
from protofuse.sai.signatures import program_signature
from protofuse.sai.trace_campaign import (
    atomic_write_json,
    clean_trace,
    cleaned_trace_summary,
    load_plan,
    require_matching_cohort_state,
)
from protofuse.sai.training import (
    load_teacher_samples,
    train_ridge_ensemble,
    validate_teacher_trace_contract,
    write_trained_fusion,
)

REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPOSITORY / "data/experiments/ligandmpnn-esmfold-joint-v3"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--ensemble-size", type=int, default=8)
    return parser


def _native_sequence(program: object) -> str:
    optimizer = program.optimizers[0]  # type: ignore[attr-defined]
    segment = optimizer.constraints[0].inputs[0]
    original = getattr(segment, "_original_sequence", None)
    sequence = getattr(original, "sequence", None)
    if not isinstance(sequence, str) or not sequence:
        raise ValueError("could not resolve the reviewed native sequence")
    return sequence


def _mutable_position_indices(
    program: object, *, optimizer_index: int, length: int
) -> tuple[int, ...]:
    optimizer = program.optimizers[optimizer_index]  # type: ignore[attr-defined]
    if len(optimizer.generators) != 1:
        raise ValueError("v3 campaign requires exactly one mutation generator")
    frozen = getattr(optimizer.generators[0].config, "frozen_positions", None)
    if not isinstance(frozen, list) or any(isinstance(value, bool) for value in frozen):
        raise ValueError("reviewed generator does not expose frozen_positions")
    frozen_indices = tuple(sorted(int(value) for value in frozen))
    if len(set(frozen_indices)) != len(frozen_indices):
        raise ValueError("reviewed generator contains duplicate frozen positions")
    if frozen_indices and (frozen_indices[0] < 0 or frozen_indices[-1] >= length):
        raise ValueError("reviewed generator frozen position is outside the native sequence")
    mutable = tuple(index for index in range(length) if index not in set(frozen_indices))
    if not mutable:
        raise ValueError("reviewed generator exposes no mutable positions")
    return mutable


def _reject_opened_external_material(root: Path) -> None:
    external_roots = (
        root / "raw/external",
        root / "clean/external",
        root / "logs/external",
        root / "quarantine/external",
    )
    material = sorted(
        path
        for directory in external_roots
        if directory.exists()
        for path in directory.rglob("*")
        if path.is_file()
    )
    if material:
        raise ValueError("external cohort material exists before development fitting")


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    if root.joinpath("artifact-freeze.json").exists():
        raise ValueError("external-test artifact is already frozen; development fitting is closed")
    plan = load_plan(root / "plan.json")
    state = json.loads((root / "state.json").read_text())
    if state.get("frozen_artifact") is not None:
        raise ValueError("campaign state already records a frozen external-test artifact")
    _reject_opened_external_material(root)
    collection = REPOSITORY / plan.collection_dir
    if file_sha256(collection / "collection.json") != plan.collection_manifest_sha256:
        raise ValueError("reviewed collection drifted after the campaign plan was frozen")
    loaded = load_reviewed_program(collection, program_id=plan.program_id)
    if program_signature(loaded.program).sha256 != plan.program_sha256:
        raise ValueError("reviewed program drifted after the campaign plan was frozen")

    development_seeds = plan.cohort("development").seeds
    expected_raw = {root / "raw/development" / f"dev-{seed}.jsonl" for seed in development_seeds}
    observed_raw = set(root.joinpath("raw/development").glob("*.jsonl"))
    if observed_raw != expected_raw:
        raise ValueError("development raw traces do not exactly match the frozen seed plan")
    cleaned = []
    seen_inputs: set[str] = set()
    for seed in development_seeds:
        raw_path = root / "raw/development" / f"dev-{seed}.jsonl"
        clean_path = root / "clean/development" / f"dev-{seed}.jsonl"
        cleaned.append(
            clean_trace(
                raw_path,
                clean_path,
                plan=plan,
                seed=seed,
                run_id=f"v3-dev-{seed}",
                group_id=f"v3-dev-{seed}",
                already_seen_inputs=seen_inputs,
            )
        )
    expected_clean = {
        root / "clean/development" / f"dev-{seed}.jsonl" for seed in development_seeds
    }
    observed_clean = set(root.joinpath("clean/development").glob("*.jsonl"))
    if observed_clean != expected_clean:
        raise ValueError("development clean traces do not exactly match the frozen seed plan")
    require_matching_cohort_state(
        state,
        plan=plan,
        cohort="development",
        items=cleaned,
    )
    external_state = state.get("cohorts", {}).get("external")
    if external_state != cleaned_trace_summary(()):
        raise ValueError("external campaign state must be empty before development fitting")
    trace_paths = tuple(Path(item.clean_path) for item in cleaned)
    validate_teacher_trace_contract(
        trace_paths,
        program=loaded.program,
        optimizer_index=plan.optimizer_index,
        constraint_labels=plan.teacher_labels,
    )
    samples = load_teacher_samples(
        trace_paths,
        optimizer_index=plan.optimizer_index,
        constraint_labels=plan.teacher_labels,
    )

    native = _native_sequence(loaded.program)
    if sha256(native.encode()).hexdigest() != plan.native_input_sha256:
        raise ValueError("reviewed native sequence drifted after the campaign plan was frozen")
    position_indices = _mutable_position_indices(
        loaded.program,
        optimizer_index=plan.optimizer_index,
        length=len(native),
    )
    one_based_positions = tuple(position + 1 for position in position_indices)
    allowed = set(position_indices)
    for sample in samples:
        [sequence] = sample.sequences
        changed = {
            index
            for index, (before, after) in enumerate(zip(native, sequence, strict=True))
            if before != after
        }
        if not changed or not changed <= allowed:
            raise ValueError("teacher sample mutation lies outside the reviewed active site")
    schema = SequenceFeatureSchema(
        sequence_type="protein",
        alphabet="ACDEFGHIKLMNPQRSTVWY",
        kmer_size=1,
        stride=1,
        include_kmers=False,
        include_composition=False,
        expected_length=len(native),
        position_encoding="one_hot",
        position_indices=position_indices,
        fixed_context_sha256=sequence_fixed_context_sha256(native, position_indices),
    )
    result = train_ridge_ensemble(
        samples,
        output_labels=plan.teacher_labels,
        trace_paths=trace_paths,
        schemas=(schema,),
        seed=plan.split_seed,
        ensemble_size=args.ensemble_size,
    )
    artifact = write_trained_fusion(
        root / "artifact",
        program=loaded.program,
        optimizer_index=plan.optimizer_index,
        constraint_labels=plan.teacher_labels,
        fusion_id=plan.campaign_id,
        version="1",
        result=result,
    )
    full_baseline_path = root / "checkpoints/100-groups/model-comparison-full.json"
    full_baseline = (
        json.loads(full_baseline_path.read_text()) if full_baseline_path.is_file() else None
    )
    report = {
        "schema_version": "1.0",
        "campaign_id": plan.campaign_id,
        "external_test_opened": False,
        "model_selection_scope": "development_only",
        "features": {
            "reviewed_active_site_positions_one_based": list(one_based_positions),
            "schema": schema.model_dump(mode="json"),
            "feature_count": schema.feature_count,
        },
        "dataset": {
            "samples": len(samples),
            "groups": len({sample.group_id for sample in samples}),
            "split": result.split.model_dump(mode="json"),
        },
        "compact_ridge": {
            "metrics": result.metrics,
            "model_sha256": artifact.manifest.model_sha256,
            "manifest_sha256": file_sha256(artifact.root / "manifest.json"),
            "reviewed": artifact.manifest.reviewed,
        },
        "full_feature_development_baseline": (
            full_baseline["models"]["linear_ensemble"] if full_baseline else None
        ),
        "selection_note": (
            "Hyperparameters were selected only by grouped inner CV inside the frozen "
            "development training groups. The external cohort remained uncollected."
        ),
    }
    atomic_write_json(root / "development-model-selection.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
