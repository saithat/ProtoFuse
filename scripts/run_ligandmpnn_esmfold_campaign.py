#!/usr/bin/env python3
"""Plan and sequentially collect the larger LigandMPNN + ESMFold cohort."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from protofuse.sai.analyzer import load_reviewed_program
from protofuse.sai.artifacts import file_sha256, load_fusion_artifact
from protofuse.sai.audit import audit_frozen_fusion
from protofuse.sai.signatures import program_signature, step_group_signature
from protofuse.sai.trace_campaign import (
    ArtifactFreeze,
    CleanedTrace,
    TraceCampaignPlan,
    TraceCohort,
    atomic_write_json,
    clean_trace,
    cleaned_trace_summary,
    load_plan,
    load_verified_artifact_freeze,
    plan_sha256,
    require_matching_cohort_state,
    write_plan,
)
from protofuse.sai.training import (
    SplitManifest,
    _sample_input_sha256,
    _split_groups,
    load_teacher_samples,
)

REPOSITORY = Path(__file__).resolve().parents[1]
COLLECTION = REPOSITORY / "proto_programs/generated/ligandmpnn-enzyme-redesign"
PROGRAM_ID = "design-002"
TRACE_LABELS = ("protein_length", "mpnn_probability", "structure_plddt")
TEACHER_LABELS = ("mpnn_probability", "structure_plddt")
DEFAULT_ROOT = REPOSITORY / "data/experiments/ligandmpnn-esmfold-joint-v3"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--development-count", type=int, default=100)
    plan.add_argument("--external-count", type=int, default=20)
    plan.add_argument("--development-start", type=int, default=10000)
    plan.add_argument("--external-start", type=int, default=20000)
    plan.add_argument("--modal-gpu", choices=("H100:1", "H200:1", "B200:1"), default="H100:1")
    plan.add_argument("--split-seed", type=int, default=42)
    collect = subparsers.add_parser("collect")
    collect.add_argument("cohort", choices=("development", "external"))
    collect.add_argument("--limit", type=int, default=None)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("artifact", type=Path)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--out", type=Path, default=None)
    subparsers.add_parser("inspect")
    return parser


def _native_hash(program: Any) -> str:
    optimizer = program.optimizers[0]
    segment = optimizer.constraints[0].inputs[0]
    original = getattr(segment, "_original_sequence", None)
    sequence = getattr(original, "sequence", None)
    if not isinstance(sequence, str) or not sequence:
        raise ValueError("could not resolve the fixed native sequence for the campaign")
    return sha256(sequence.encode()).hexdigest()


def _create_plan(args: argparse.Namespace) -> TraceCampaignPlan:
    if args.development_count < 5 or args.external_count < 4:
        raise ValueError("campaign requires at least five development and four external groups")
    loaded = load_reviewed_program(COLLECTION, program_id=PROGRAM_ID)
    program = loaded.program
    optimizer = program.optimizers[0]
    observed_labels = tuple(sorted(constraint.label for constraint in optimizer.constraints))
    if observed_labels != tuple(sorted(TRACE_LABELS)):
        raise ValueError(f"unexpected score-only constraint group: {observed_labels}")
    calls_per_label = int(optimizer.num_steps) + 1
    return TraceCampaignPlan(
        campaign_id="ligandmpnn-esmfold-joint-v3",
        collection_dir=str(COLLECTION.relative_to(REPOSITORY)),
        collection_id=loaded.collection.manifest.collection_id,
        collection_manifest_sha256=file_sha256(COLLECTION / "collection.json"),
        program_id=PROGRAM_ID,
        methodology_id=loaded.collection.manifest.methodology_id,
        program_sha256=program_signature(program).sha256,
        optimizer_index=0,
        trace_labels=TRACE_LABELS,
        teacher_labels=TEACHER_LABELS,
        native_input_sha256=_native_hash(program),
        expected_calls_per_label=calls_per_label,
        expected_rows=calls_per_label * len(TRACE_LABELS),
        modal_gpu=args.modal_gpu,
        split_seed=args.split_seed,
        cohorts=(
            TraceCohort(
                name="development",
                seeds=tuple(
                    range(args.development_start, args.development_start + args.development_count)
                ),
            ),
            TraceCohort(
                name="external",
                seeds=tuple(range(args.external_start, args.external_start + args.external_count)),
            ),
        ),
    )


def _state_path(root: Path) -> Path:
    return root / "state.json"


def _load_state(root: Path, plan: TraceCampaignPlan) -> dict[str, Any]:
    path = _state_path(root)
    if not path.exists():
        return {
            "schema_version": "1.0",
            "campaign_id": plan.campaign_id,
            "plan_sha256": plan_sha256(plan),
            "frozen_artifact": None,
            "cohorts": {},
        }
    state = json.loads(path.read_text())
    if state.get("plan_sha256") != plan_sha256(plan):
        raise ValueError("campaign state does not match the frozen plan")
    return state


def _save_state(root: Path, state: dict[str, Any]) -> None:
    atomic_write_json(_state_path(root), state)


def _paths(root: Path, cohort: str, seed: int) -> tuple[Path, Path, Path]:
    prefix = "dev" if cohort == "development" else "external"
    return (
        root / "raw" / cohort / f"{prefix}-{seed}.jsonl",
        root / "clean" / cohort / f"{prefix}-{seed}.jsonl",
        root / "logs" / cohort / f"{prefix}-{seed}.log",
    )


def _ids(cohort: str, seed: int) -> tuple[str, str]:
    prefix = "v3-dev" if cohort == "development" else "v3-external"
    value = f"{prefix}-{seed}"
    return value, value


def _quarantine(root: Path, cohort: str, raw_path: Path) -> None:
    if not raw_path.exists():
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = root / "quarantine" / cohort / f"{raw_path.stem}.{stamp}.partial.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(raw_path, destination)


def _rebuild_clean(root: Path, plan: TraceCampaignPlan) -> dict[str, list[CleanedTrace]]:
    results: dict[str, list[CleanedTrace]] = {"development": [], "external": []}
    seen: set[str] = set()
    for cohort_name in ("development", "external"):
        if cohort_name == "external" and not root.joinpath("artifact-freeze.json").exists():
            continue
        for seed in plan.cohort(cohort_name).seeds:
            raw, clean, _ = _paths(root, cohort_name, seed)
            if not raw.exists():
                continue
            run_id, group_id = _ids(cohort_name, seed)
            result = clean_trace(
                raw,
                clean,
                plan=plan,
                seed=seed,
                run_id=run_id,
                group_id=group_id,
                already_seen_inputs=seen,
            )
            results[cohort_name].append(result)
    return results


def _summaries(results: dict[str, list[CleanedTrace]]) -> dict[str, Any]:
    return {cohort: cleaned_trace_summary(items) for cohort, items in results.items()}


def _validated_program(plan: TraceCampaignPlan) -> Any:
    collection = REPOSITORY / plan.collection_dir
    if file_sha256(collection / "collection.json") != plan.collection_manifest_sha256:
        raise ValueError("reviewed collection drifted after the campaign plan was frozen")
    loaded = load_reviewed_program(collection, program_id=plan.program_id)
    if loaded.collection.manifest.collection_id != plan.collection_id:
        raise ValueError("reviewed collection ID differs from the frozen campaign")
    if loaded.collection.manifest.methodology_id != plan.methodology_id:
        raise ValueError("reviewed methodology ID differs from the frozen campaign")
    if program_signature(loaded.program).sha256 != plan.program_sha256:
        raise ValueError("reviewed program drifted after the campaign plan was frozen")
    if _native_hash(loaded.program) != plan.native_input_sha256:
        raise ValueError("reviewed native sequence drifted after the campaign plan was frozen")
    return loaded.program


def _require_complete_cohort(
    results: dict[str, list[CleanedTrace]],
    plan: TraceCampaignPlan,
    cohort: str,
) -> None:
    expected = plan.cohort(cohort).seeds
    observed = tuple(item.seed for item in results[cohort])
    if observed != expected:
        raise ValueError(f"{cohort} traces do not exactly cover the frozen seed plan")


def _external_material(root: Path) -> tuple[Path, ...]:
    directories = (
        root / "raw/external",
        root / "clean/external",
        root / "logs/external",
        root / "quarantine/external",
    )
    return tuple(
        sorted(
            path
            for directory in directories
            if directory.exists()
            for path in directory.rglob("*")
            if path.is_file()
        )
    )


def _reject_unplanned_trace_files(
    root: Path,
    *,
    plan: TraceCampaignPlan,
    cohort: str,
) -> None:
    expected_raw = {_paths(root, cohort, seed)[0] for seed in plan.cohort(cohort).seeds}
    expected_clean = {_paths(root, cohort, seed)[1] for seed in plan.cohort(cohort).seeds}
    observed_raw = set(root.joinpath("raw", cohort).glob("*.jsonl"))
    observed_clean = set(root.joinpath("clean", cohort).glob("*.jsonl"))
    if not observed_raw <= expected_raw or not observed_clean <= expected_clean:
        raise ValueError(f"{cohort} contains trace files outside the frozen seed plan")


def _validate_artifact_contract(
    artifact_dir: Path,
    *,
    plan: TraceCampaignPlan,
    program: Any,
    development: list[CleanedTrace],
) -> None:
    _require_complete_cohort({"development": development}, plan, "development")
    artifact = load_fusion_artifact(artifact_dir, require_reviewed=False)
    manifest = artifact.manifest
    if any(
        schema.position_indices is not None and schema.fixed_context_sha256 is None
        for schema in artifact.model.input_schemas
    ):
        raise ValueError("campaign artifact selected positions do not freeze sequence context")
    if manifest.fusion_id != plan.campaign_id:
        raise ValueError("artifact fusion ID does not match the campaign")
    if (
        manifest.optimizer_index != plan.optimizer_index
        or manifest.constraint_labels != plan.teacher_labels
    ):
        raise ValueError("artifact target group does not match the campaign")
    expected_signature = step_group_signature(
        program,
        optimizer_index=plan.optimizer_index,
        constraint_labels=plan.teacher_labels,
    )
    if manifest.group_signature_sha256 != expected_signature.sha256:
        raise ValueError("artifact group signature does not match the frozen program")
    expected_trace_hashes = tuple(item.clean_sha256 for item in development)
    if manifest.training_trace_sha256 != expected_trace_hashes:
        raise ValueError("artifact training traces do not exactly match the development cohort")

    split_path = artifact.root / "split.json"
    if split_path.is_symlink() or not split_path.is_file():
        raise ValueError("artifact split manifest is missing or unsafe")
    if (
        manifest.split_manifest_sha256 is None
        or file_sha256(split_path) != manifest.split_manifest_sha256
    ):
        raise ValueError("artifact split manifest hash mismatch")
    split = SplitManifest.model_validate_json(split_path.read_text())
    if split.seed != plan.split_seed or split.trace_sha256 != expected_trace_hashes:
        raise ValueError("artifact split does not match campaign seed or trace hashes")
    samples = load_teacher_samples(
        tuple(Path(item.clean_path) for item in development),
        optimizer_index=plan.optimizer_index,
        constraint_labels=plan.teacher_labels,
    )
    expected_inputs = tuple(sorted(_sample_input_sha256(sample.sequences) for sample in samples))
    if split.input_sha256 != expected_inputs:
        raise ValueError("artifact split input hashes do not match the development cohort")
    split_groups = (
        set(split.train_groups),
        set(split.calibration_groups),
        set(split.audit_groups),
    )
    if any(
        left & right
        for index, left in enumerate(split_groups)
        for right in split_groups[index + 1 :]
    ):
        raise ValueError("artifact split groups overlap")
    expected_groups = {item.group_id for item in development}
    if set().union(*split_groups) != expected_groups:
        raise ValueError("artifact split groups do not exactly match the development cohort")
    expected_split_groups = _split_groups(expected_groups, plan.split_seed)
    if split_groups != expected_split_groups:
        raise ValueError("artifact split assignment differs from the deterministic campaign split")
    expected_sample_counts = tuple(
        sum(sample.group_id in groups for sample in samples) for groups in split_groups
    )
    if (
        split.train_samples,
        split.calibration_samples,
        split.audit_samples,
    ) != expected_sample_counts:
        raise ValueError("artifact split sample counts do not match the development cohort")


def _verify_campaign_freeze(
    root: Path,
    *,
    plan: TraceCampaignPlan,
    state: dict[str, Any],
    program: Any,
) -> tuple[ArtifactFreeze, dict[str, list[CleanedTrace]]]:
    freeze = load_verified_artifact_freeze(root / "artifact-freeze.json", plan=plan)
    if state.get("frozen_artifact") != freeze.model_dump(mode="json"):
        raise ValueError("campaign state and artifact freeze record disagree")
    results = _rebuild_clean(root, plan)
    _require_complete_cohort(results, plan, "development")
    require_matching_cohort_state(
        state,
        plan=plan,
        cohort="development",
        items=results["development"],
    )
    _validate_artifact_contract(
        Path(freeze.artifact),
        plan=plan,
        program=program,
        development=results["development"],
    )
    return freeze, results


def _run_trace(root: Path, plan: TraceCampaignPlan, cohort: str, seed: int) -> None:
    raw, _, log = _paths(root, cohort, seed)
    raw.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    run_id, group_id = _ids(cohort, seed)
    command = [
        sys.executable,
        "-m",
        "protofuse.cli",
        "trace",
        plan.collection_dir,
        plan.program_id,
        "--out",
        str(raw),
        "--run-id",
        run_id,
        "--group-id",
        group_id,
        "--seed",
        str(seed),
        "--device",
        plan.device,
        "--modal-gpu",
        plan.modal_gpu,
        "--tier",
        plan.tier,
    ]
    environment = dict(os.environ)
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            command,
            cwd=REPOSITORY,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        _quarantine(root, cohort, raw)
        raise RuntimeError(f"trace seed {seed} failed with exit {completed.returncode}; see {log}")


def _collect(
    args: argparse.Namespace,
    root: Path,
    plan: TraceCampaignPlan,
    program: Any,
) -> None:
    state = _load_state(root, plan)
    _reject_unplanned_trace_files(root, plan=plan, cohort=args.cohort)
    freeze_path = root / "artifact-freeze.json"
    if args.cohort == "development" and freeze_path.exists():
        raise ValueError("development collection is closed after the external artifact freeze")
    if args.cohort == "external":
        if state.get("frozen_artifact") is None:
            raise ValueError("freeze the final development artifact before opening external traces")
        _, results = _verify_campaign_freeze(
            root,
            plan=plan,
            state=state,
            program=program,
        )
        require_matching_cohort_state(
            state,
            plan=plan,
            cohort="external",
            items=results["external"],
        )
    else:
        results = _rebuild_clean(root, plan)
    cohort = plan.cohort(args.cohort)
    completed = {item.seed for item in results[args.cohort]}
    remaining = [seed for seed in cohort.seeds if seed not in completed]
    selected = remaining if args.limit is None else remaining[: args.limit]
    for index, seed in enumerate(selected, start=1):
        if args.cohort == "external":
            verified = load_verified_artifact_freeze(freeze_path, plan=plan)
            if state.get("frozen_artifact") != verified.model_dump(mode="json"):
                raise ValueError("campaign state and artifact freeze record disagree")
        raw, _, _ = _paths(root, args.cohort, seed)
        if raw.exists():
            _quarantine(root, args.cohort, raw)
        print(
            f"collecting {args.cohort} seed {seed} "
            f"({index}/{len(selected)}, sequential {plan.modal_gpu})",
            flush=True,
        )
        _run_trace(root, plan, args.cohort, seed)
        results = _rebuild_clean(root, plan)
        state["cohorts"] = _summaries(results)
        _save_state(root, state)
        latest = next(item for item in results[args.cohort] if item.seed == seed)
        print(
            f"accepted seed {seed}: {latest.teacher_samples} unique teacher samples, "
            f"{latest.duplicate_samples_removed} duplicates removed",
            flush=True,
        )
    if args.cohort == "external":
        load_verified_artifact_freeze(freeze_path, plan=plan)


def _freeze(
    args: argparse.Namespace,
    root: Path,
    plan: TraceCampaignPlan,
    program: Any,
) -> None:
    artifact = args.artifact.resolve()
    state = _load_state(root, plan)
    if _external_material(root):
        raise ValueError("external cohort material exists before the artifact freeze")
    results = _rebuild_clean(root, plan)
    _require_complete_cohort(results, plan, "development")
    require_matching_cohort_state(
        state,
        plan=plan,
        cohort="development",
        items=results["development"],
    )
    if state.get("cohorts", {}).get("external") != cleaned_trace_summary(()):
        raise ValueError("external campaign state must be empty before the artifact freeze")
    _validate_artifact_contract(
        artifact,
        plan=plan,
        program=program,
        development=results["development"],
    )
    required = tuple(artifact / name for name in ("manifest.json", "model.json", "split.json"))
    payload = ArtifactFreeze(
        artifact=str(artifact),
        files={path.name: file_sha256(path) for path in required},
        frozen_at=datetime.now(UTC).isoformat(),
        plan_sha256=plan_sha256(plan),
    ).model_dump(mode="json")
    freeze_path = root / "artifact-freeze.json"
    if freeze_path.exists() and json.loads(freeze_path.read_text()) != payload:
        existing = json.loads(freeze_path.read_text())
        comparable = {key: value for key, value in payload.items() if key != "frozen_at"}
        existing_comparable = {key: value for key, value in existing.items() if key != "frozen_at"}
        if existing_comparable != comparable:
            raise ValueError("a different artifact is already frozen for this external cohort")
        payload = existing
    atomic_write_json(freeze_path, payload)
    state["frozen_artifact"] = payload
    _save_state(root, state)
    load_verified_artifact_freeze(freeze_path, plan=plan)
    print(f"frozen artifact: {artifact}")


def _audit(
    args: argparse.Namespace,
    root: Path,
    plan: TraceCampaignPlan,
    program: Any,
) -> None:
    state = _load_state(root, plan)
    _reject_unplanned_trace_files(root, plan=plan, cohort="development")
    _reject_unplanned_trace_files(root, plan=plan, cohort="external")
    freeze, results = _verify_campaign_freeze(
        root,
        plan=plan,
        state=state,
        program=program,
    )
    _require_complete_cohort(results, plan, "external")
    require_matching_cohort_state(
        state,
        plan=plan,
        cohort="external",
        items=results["external"],
    )
    report = audit_frozen_fusion(
        Path(freeze.artifact),
        tuple(Path(item.clean_path) for item in results["external"]),
        min_groups=len(plan.cohort("external").seeds),
        require_reviewed=False,
    )
    report["provenance"]["campaign_plan_sha256"] = plan_sha256(plan)
    report["provenance"]["artifact_freeze_sha256"] = file_sha256(root / "artifact-freeze.json")
    output = (args.out or root / "audit.json").resolve()
    atomic_write_json(output, report)
    print(f"audit={output}")
    if not report["passed"]:
        raise SystemExit(1)


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    plan_path = root / "plan.json"
    if args.command == "plan":
        plan = _create_plan(args)
        write_plan(plan_path, plan)
        state = _load_state(root, plan)
        _save_state(root, state)
        print(plan.model_dump_json(indent=2))
        return
    plan = load_plan(plan_path)
    program = _validated_program(plan)
    if args.command == "collect":
        _collect(args, root, plan, program)
        return
    if args.command == "freeze":
        _freeze(args, root, plan, program)
        return
    if args.command == "audit":
        _audit(args, root, plan, program)
        return
    if args.command == "inspect":
        state = _load_state(root, plan)
        if root.joinpath("artifact-freeze.json").exists():
            freeze = load_verified_artifact_freeze(root / "artifact-freeze.json", plan=plan)
            if state.get("frozen_artifact") != freeze.model_dump(mode="json"):
                raise ValueError("campaign state and artifact freeze record disagree")
        results = _rebuild_clean(root, plan)
        state["cohorts"] = _summaries(results)
        _save_state(root, state)
        print(json.dumps(state, indent=2, sort_keys=True))
        return
    raise AssertionError(args.command)


if __name__ == "__main__":
    main()
