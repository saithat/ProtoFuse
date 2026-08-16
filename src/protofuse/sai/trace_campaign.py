"""Resumable, leakage-resistant planning for multi-seed teacher trace campaigns."""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from protofuse.sai.artifacts import file_sha256
from protofuse.sai.tracing import TraceRow


class TraceCohort(BaseModel):
    """One predeclared group of independent optimizer trajectories."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["development", "external"]
    seeds: tuple[int, ...]

    @model_validator(mode="after")
    def seeds_are_nonempty_and_unique(self) -> TraceCohort:
        if not self.seeds:
            raise ValueError("campaign cohort seeds cannot be empty")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError(f"campaign cohort {self.name!r} contains duplicate seeds")
        return self


class TraceCampaignPlan(BaseModel):
    """Immutable inputs and contracts for one trace campaign."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    campaign_id: str
    collection_dir: str
    collection_id: str
    collection_manifest_sha256: str
    program_id: str
    methodology_id: str
    program_sha256: str
    optimizer_index: int = Field(ge=0)
    trace_labels: tuple[str, ...]
    teacher_labels: tuple[str, ...]
    native_input_sha256: str
    expected_calls_per_label: int = Field(ge=2)
    expected_rows: int = Field(ge=1)
    tier: Literal["smoke"] = "smoke"
    device: Literal["modal"] = "modal"
    modal_gpu: Literal["H100:1", "H200:1", "B200:1"]
    split_seed: int
    cohorts: tuple[TraceCohort, TraceCohort]

    @model_validator(mode="after")
    def campaign_contract_is_consistent(self) -> TraceCampaignPlan:
        names = tuple(cohort.name for cohort in self.cohorts)
        if sorted(names) != ["development", "external"]:
            raise ValueError("campaign requires exactly one development and one external cohort")
        development = self.cohort("development")
        external = self.cohort("external")
        overlap = set(development.seeds) & set(external.seeds)
        if overlap:
            raise ValueError(f"campaign cohort seeds overlap: {sorted(overlap)}")
        if not self.trace_labels or len(set(self.trace_labels)) != len(self.trace_labels):
            raise ValueError("trace labels must be non-empty and unique")
        if not self.teacher_labels or len(set(self.teacher_labels)) != len(self.teacher_labels):
            raise ValueError("teacher labels must be non-empty and unique")
        if not set(self.teacher_labels) <= set(self.trace_labels):
            raise ValueError("teacher labels must be a subset of trace labels")
        expected_rows = self.expected_calls_per_label * len(self.trace_labels)
        if self.expected_rows != expected_rows:
            raise ValueError(
                f"expected_rows must equal calls per label times trace labels ({expected_rows})"
            )
        return self

    def cohort(self, name: str) -> TraceCohort:
        matches = tuple(cohort for cohort in self.cohorts if cohort.name == name)
        if len(matches) != 1:
            raise ValueError(f"campaign plan must contain exactly one {name!r} cohort")
        return matches[0]


class CleanedTrace(BaseModel):
    """Auditable result of validating and cleaning one raw trajectory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    run_id: str
    group_id: str
    raw_path: str
    clean_path: str
    raw_sha256: str
    clean_sha256: str
    raw_rows: int
    clean_rows: int
    teacher_samples: int
    duplicate_samples_removed: int
    unique_input_sha256: tuple[str, ...]


class ArtifactFreeze(BaseModel):
    """Immutable byte-level record opened before the external cohort."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact: str
    files: dict[str, str]
    frozen_at: str
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def required_files_are_exact_hashes(self) -> ArtifactFreeze:
        required = {"manifest.json", "model.json", "split.json"}
        if set(self.files) != required:
            raise ValueError(f"artifact freeze must hash exactly {sorted(required)}")
        if any(
            len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
            for digest in self.files.values()
        ):
            raise ValueError("artifact freeze contains an invalid SHA-256 digest")
        return self


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON without exposing a partially updated campaign file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    temporary.replace(path)


def write_plan(path: Path, plan: TraceCampaignPlan) -> None:
    """Create a plan once; an identical rerun is harmless."""

    payload = plan.model_dump(mode="json")
    if path.exists():
        current = TraceCampaignPlan.model_validate_json(path.read_text())
        if current != plan:
            raise ValueError("campaign plan already exists with different frozen inputs")
        return
    atomic_write_json(path, payload)


def load_plan(path: Path) -> TraceCampaignPlan:
    return TraceCampaignPlan.model_validate_json(path.read_text())


def plan_sha256(plan: TraceCampaignPlan) -> str:
    payload = plan.model_dump_json(exclude_none=False)
    return sha256(payload.encode()).hexdigest()


def cleaned_trace_summary(items: Sequence[CleanedTrace]) -> dict[str, Any]:
    """Build the canonical state entry for one validated cohort."""

    return {
        "completed_groups": len(items),
        "raw_rows": sum(item.raw_rows for item in items),
        "clean_rows": sum(item.clean_rows for item in items),
        "teacher_samples": sum(item.teacher_samples for item in items),
        "duplicate_samples_removed": sum(item.duplicate_samples_removed for item in items),
        "traces": [item.model_dump(mode="json") for item in items],
    }


def require_matching_cohort_state(
    state: Mapping[str, Any],
    *,
    plan: TraceCampaignPlan,
    cohort: str,
    items: Sequence[CleanedTrace],
) -> None:
    """Reject a mutable campaign index that disagrees with raw-derived traces."""

    if state.get("campaign_id") != plan.campaign_id:
        raise ValueError("campaign state ID does not match the frozen plan")
    if state.get("plan_sha256") != plan_sha256(plan):
        raise ValueError("campaign state does not match the frozen plan")
    observed = state.get("cohorts", {}).get(cohort)
    expected = cleaned_trace_summary(items)
    if observed != expected:
        raise ValueError(f"campaign state for {cohort!r} differs from raw-derived traces")


def load_verified_artifact_freeze(
    path: Path,
    *,
    plan: TraceCampaignPlan,
) -> ArtifactFreeze:
    """Load a freeze record and prove every recorded artifact byte is unchanged."""

    if path.is_symlink() or not path.is_file():
        raise ValueError("artifact freeze record is missing or unsafe")
    freeze = ArtifactFreeze.model_validate_json(path.read_text())
    if freeze.plan_sha256 != plan_sha256(plan):
        raise ValueError("artifact freeze does not match the frozen campaign plan")
    unresolved_root = Path(freeze.artifact)
    if not unresolved_root.is_absolute() or unresolved_root.is_symlink():
        raise ValueError("frozen artifact path must be an absolute non-symlink directory")
    root = unresolved_root.resolve()
    if not root.is_dir():
        raise ValueError("frozen artifact directory is missing")
    for name, expected_sha256 in freeze.files.items():
        unresolved = root / name
        if unresolved.is_symlink() or not unresolved.is_file():
            raise ValueError(f"frozen artifact file is missing or unsafe: {name}")
        if unresolved.resolve().parent != root:
            raise ValueError(f"frozen artifact file escapes its directory: {name}")
        if file_sha256(unresolved) != expected_sha256:
            raise ValueError(f"frozen artifact file changed after external-test lock: {name}")
    return freeze


def _read_rows(path: Path) -> list[TraceRow]:
    rows: list[TraceRow] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(TraceRow.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"invalid trace row {path}:{line_number}: {exc}") from exc
    return rows


def _validate_row_contract(
    row: TraceRow,
    *,
    plan: TraceCampaignPlan,
    seed: int,
    run_id: str,
    group_id: str,
) -> None:
    if row.schema_version != "1.1" or row.constraint_config_scope != "pre_run_contract":
        raise ValueError("campaign requires trace schema 1.1 pre-run contracts")
    if (
        row.program_sha256 != plan.program_sha256
        or row.program_seed != seed
        or row.run_id != run_id
        or row.group_id != group_id
        or row.collection_id != plan.collection_id
        or row.program_id != plan.program_id
        or row.methodology_id != plan.methodology_id
        or row.tier != plan.tier
        or row.optimizer_index != plan.optimizer_index
    ):
        raise ValueError("trace row differs from the frozen campaign contract")
    if row.constraint_label not in plan.trace_labels:
        raise ValueError(f"unexpected constraint label {row.constraint_label!r}")
    if row.error is not None or row.score is None or row.input_sequences is None:
        raise ValueError("trace contains a failed or incomplete teacher row")
    if row.has_structures or row.has_logits:
        raise ValueError("campaign accepts score-only constraint outputs")
    if len(row.input_sha256) != 1 or len(row.input_sequences) != 1:
        raise ValueError("campaign expects exactly one sequence input per row")
    observed = sha256(row.input_sequences[0].encode()).hexdigest()
    if row.input_sha256[0] != observed:
        raise ValueError("trace input sequence does not match its recorded hash")


def clean_trace(
    raw_path: Path,
    clean_path: Path,
    *,
    plan: TraceCampaignPlan,
    seed: int,
    run_id: str,
    group_id: str,
    already_seen_inputs: set[str],
) -> CleanedTrace:
    """Validate one complete trajectory and remove baseline/leaking duplicates."""

    rows = _read_rows(raw_path)
    if len(rows) != plan.expected_rows:
        raise ValueError(f"trace has {len(rows)} rows; expected exactly {plan.expected_rows}")
    for row in rows:
        _validate_row_contract(
            row,
            plan=plan,
            seed=seed,
            run_id=run_id,
            group_id=group_id,
        )
    counts = Counter(row.constraint_label for row in rows)
    expected_counts = Counter({label: plan.expected_calls_per_label for label in plan.trace_labels})
    if counts != expected_counts:
        raise ValueError(
            f"trace label counts differ: observed={dict(counts)}, expected={dict(expected_counts)}"
        )

    ordered = sorted(rows, key=lambda row: (row.call_index, row.proposal_index))
    width = len(plan.trace_labels)
    triplets = tuple(ordered[index : index + width] for index in range(0, len(ordered), width))
    if any(len(batch) != width for batch in triplets):
        raise ValueError("trace rows cannot be partitioned into aligned constraint batches")
    for batch in triplets:
        hashes = {row.input_sha256 for row in batch}
        labels = {row.constraint_label for row in batch}
        if len(hashes) != 1 or labels != set(plan.trace_labels):
            raise ValueError("trace constraint batch is incomplete or input-misaligned")

    if triplets[0][0].input_sha256[0] != plan.native_input_sha256:
        raise ValueError("trace must begin with the native baseline batch")

    kept: list[TraceRow] = []
    unique_inputs: list[str] = []
    duplicates = 0
    # The optimizer may legitimately return to the native sequence after a rejected
    # or reversing mutation. Treat every such recurrence as baseline leakage too.
    seen = {plan.native_input_sha256, *already_seen_inputs}
    for batch in triplets[1:]:
        input_hash = batch[0].input_sha256[0]
        if input_hash in seen:
            duplicates += 1
            continue
        seen.add(input_hash)
        unique_inputs.append(input_hash)
        kept.extend(batch)

    clean_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = clean_path.with_name(f".{clean_path.name}.tmp")
    temporary.write_text("".join(row.model_dump_json() + "\n" for row in kept))
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    temporary.replace(clean_path)
    already_seen_inputs.update(unique_inputs)
    return CleanedTrace(
        seed=seed,
        run_id=run_id,
        group_id=group_id,
        raw_path=str(raw_path),
        clean_path=str(clean_path),
        raw_sha256=file_sha256(raw_path),
        clean_sha256=file_sha256(clean_path),
        raw_rows=len(rows),
        clean_rows=len(kept),
        teacher_samples=len(unique_inputs),
        duplicate_samples_removed=duplicates,
        unique_input_sha256=tuple(unique_inputs),
    )
