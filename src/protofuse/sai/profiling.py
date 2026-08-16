"""Observed constraint-call profiles derived from append-only teacher traces."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from protofuse.sai.artifacts import file_sha256
from protofuse.sai.tracing import TraceRow


class ConstraintProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    optimizer_index: int = Field(ge=0)
    constraint_label: str
    constraint_identity: str
    calls: int = Field(ge=0)
    proposals: int = Field(ge=0)
    failed_calls: int = Field(ge=0)
    total_parent_seconds: float = Field(ge=0)
    p50_call_seconds: float = Field(ge=0)
    p95_call_seconds: float = Field(ge=0)
    structure_output_proposals: int = Field(ge=0)
    logits_output_proposals: int = Field(ge=0)
    accelerator_seconds: float | None = None
    peak_memory_bytes: int | None = None
    estimated_cost: float | None = None


class TraceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    trace_sha256: tuple[str, ...]
    constraints: tuple[ConstraintProfile, ...]


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * probability)))
    return ordered[index]


def profile_traces(trace_paths: tuple[Path, ...]) -> TraceProfile:
    """Count actual calls once per batch and preserve unavailable measurements as null."""

    if not trace_paths:
        raise ValueError("profiling requires at least one trace")
    calls: dict[
        tuple[str, str, str, int, str, int],
        list[TraceRow],
    ] = defaultdict(list)
    for path in trace_paths:
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = TraceRow.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"invalid trace row {path}:{line_number}: {exc}") from exc
            calls[
                (
                    row.program_sha256,
                    row.run_id,
                    row.group_id,
                    row.optimizer_index,
                    row.constraint_label,
                    row.call_index,
                )
            ].append(row)

    grouped: dict[tuple[int, str, str], list[list[TraceRow]]] = defaultdict(list)
    for rows in calls.values():
        first = rows[0]
        grouped[(first.optimizer_index, first.constraint_label, first.constraint_identity)].append(
            rows
        )

    profiles: list[ConstraintProfile] = []
    for (optimizer_index, label, identity), batches in sorted(grouped.items()):
        latencies = [max(row.call_latency_seconds for row in batch) for batch in batches]
        profiles.append(
            ConstraintProfile(
                optimizer_index=optimizer_index,
                constraint_label=label,
                constraint_identity=identity,
                calls=len(batches),
                proposals=sum(len(batch) for batch in batches),
                failed_calls=sum(any(row.error is not None for row in batch) for batch in batches),
                total_parent_seconds=sum(latencies),
                p50_call_seconds=float(median(latencies)),
                p95_call_seconds=_percentile(latencies, 0.95),
                structure_output_proposals=sum(
                    row.has_structures for batch in batches for row in batch
                ),
                logits_output_proposals=sum(row.has_logits for batch in batches for row in batch),
            )
        )
    return TraceProfile(
        trace_sha256=tuple(file_sha256(path) for path in trace_paths),
        constraints=tuple(profiles),
    )
