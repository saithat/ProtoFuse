"""Append-only teacher tracing for real Proto constraint evaluations."""

from __future__ import annotations

import functools
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from itertools import count
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast

from proto_language.core import ConstraintOutput, Program
from proto_language.core import Sequence as ProtoSequence
from pydantic import BaseModel, ConfigDict, Field, model_validator

from protofuse.sai.signatures import callable_signature, stable_data


class TraceRow(BaseModel):
    """One parent-objective result for one proposal."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "1.1"] = "1.0"
    constraint_config_scope: Literal["pre_run_contract"] | None = None
    recorded_at: str
    run_id: str
    group_id: str
    collection_id: str | None = None
    program_id: str | None = None
    methodology_id: str | None = None
    tier: str | None = None
    program_seed: int | None = None
    program_sha256: str
    optimizer_index: int
    constraint_label: str
    constraint_identity: str
    constraint_config: Any = None
    constraint_threshold: float | None = None
    constraint_weight: float = 1.0
    call_index: int = Field(ge=0)
    proposal_index: int = Field(ge=0)
    input_sha256: tuple[str, ...]
    input_sequences: tuple[str, ...] | None
    input_structure_sha256: tuple[str | None, ...]
    score: float | None
    metadata: Any
    has_structures: bool
    has_logits: bool
    call_latency_seconds: float
    error: str | None = None

    @model_validator(mode="after")
    def config_scope_matches_schema(self) -> TraceRow:
        if self.schema_version == "1.1" and self.constraint_config_scope != "pre_run_contract":
            raise ValueError("trace schema 1.1 requires pre_run_contract config scope")
        if self.schema_version == "1.0" and self.constraint_config_scope is not None:
            raise ValueError("trace schema 1.0 cannot declare a config scope")
        return self


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _structure_hash(sequence: ProtoSequence) -> str | None:
    structure = getattr(sequence, "structure", None)
    text = getattr(structure, "structure", None)
    return sha256(text.encode()).hexdigest() if isinstance(text, str) else None


class JsonlTraceWriter:
    """Crash-tolerant JSONL writer; raw traces remain under ignored data paths."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write_many(self, rows: Sequence[TraceRow]) -> None:
        if not rows:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(row.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())


@contextmanager
def trace_program_constraints(
    program: Program,
    writer: JsonlTraceWriter,
    *,
    run_id: str,
    group_id: str,
    group_by_input_batch: bool = False,
    include_inputs: bool = True,
    collection_id: str | None = None,
    program_id: str | None = None,
    methodology_id: str | None = None,
    tier: str | None = None,
) -> Iterator[None]:
    """Temporarily wrap every discrete constraint and restore it afterward."""

    from protofuse.sai.signatures import program_signature

    signature_hash = program_signature(program).sha256
    call_counter = count()
    originals: list[tuple[Any, Any]] = []

    for optimizer_index, optimizer in enumerate(program.optimizers):
        for constraint in optimizer.constraints:
            original = constraint.function
            if original is None:
                continue
            identity = callable_signature(original)
            identity_text = identity.identity if identity else "unknown"
            # Optimizers inject derived runtime seeds into constraint configs at the
            # start of ``run()``. Keep the trace contract equal to the pre-run
            # program signature; ``program_seed`` records execution randomness.
            contract_config = stable_data(constraint.function_config)
            contract_threshold = constraint.threshold
            contract_weight = float(constraint.weight)

            @functools.wraps(original)
            def traced(
                input_sequences: list[tuple[ProtoSequence, ...]],
                config: Any,
                *,
                _original: Any = original,
                _optimizer_index: int = optimizer_index,
                _constraint: Any = constraint,
                _identity: str = identity_text,
                _contract_config: Any = contract_config,
                _contract_threshold: float | None = contract_threshold,
                _contract_weight: float = contract_weight,
            ) -> list[ConstraintOutput]:
                call_index = next(call_counter)
                resolved_group_id = (
                    _input_batch_group_id(group_id, input_sequences)
                    if group_by_input_batch
                    else group_id
                )
                started = perf_counter()
                try:
                    outputs = list(_original(input_sequences, config=config))
                except Exception as error:
                    elapsed = perf_counter() - started
                    rows = [
                        _trace_row(
                            inputs=inputs,
                            output=None,
                            recorded_at=_utc_now(),
                            run_id=run_id,
                            group_id=resolved_group_id,
                            collection_id=collection_id,
                            program_id=program_id,
                            methodology_id=methodology_id,
                            tier=tier,
                            program_seed=program.seed,
                            program_sha256=signature_hash,
                            optimizer_index=_optimizer_index,
                            constraint_label=str(_constraint.label),
                            constraint_identity=_identity,
                            constraint_config=_contract_config,
                            constraint_threshold=_contract_threshold,
                            constraint_weight=_contract_weight,
                            call_index=call_index,
                            proposal_index=proposal_index,
                            include_inputs=include_inputs,
                            latency=elapsed,
                            error=f"{type(error).__name__}:{error}",
                        )
                        for proposal_index, inputs in enumerate(input_sequences)
                    ]
                    writer.write_many(rows)
                    raise
                elapsed = perf_counter() - started
                if len(outputs) != len(input_sequences):
                    raise ValueError(
                        f"traced constraint {_constraint.label!r} returned {len(outputs)} "
                        f"outputs for {len(input_sequences)} inputs"
                    )
                writer.write_many(
                    [
                        _trace_row(
                            inputs=inputs,
                            output=output,
                            recorded_at=_utc_now(),
                            run_id=run_id,
                            group_id=resolved_group_id,
                            collection_id=collection_id,
                            program_id=program_id,
                            methodology_id=methodology_id,
                            tier=tier,
                            program_seed=program.seed,
                            program_sha256=signature_hash,
                            optimizer_index=_optimizer_index,
                            constraint_label=str(_constraint.label),
                            constraint_identity=_identity,
                            constraint_config=_contract_config,
                            constraint_threshold=_contract_threshold,
                            constraint_weight=_contract_weight,
                            call_index=call_index,
                            proposal_index=proposal_index,
                            include_inputs=include_inputs,
                            latency=elapsed,
                            error=None,
                        )
                        for proposal_index, (inputs, output) in enumerate(
                            zip(input_sequences, outputs, strict=True)
                        )
                    ]
                )
                return outputs

            if bool(getattr(original, "_constraint_allow_raw_scores", False)):
                cast(Any, traced)._constraint_allow_raw_scores = True
            originals.append((constraint, original))
            constraint._function = traced

    try:
        yield
    finally:
        for constraint, original in originals:
            constraint._function = original


def _input_batch_group_id(
    base_group_id: str,
    input_sequences: list[tuple[ProtoSequence, ...]],
) -> str:
    """Group sibling proposals together without recording their raw sequence in the ID."""

    digest = sha256()
    for inputs in input_sequences:
        digest.update(len(inputs).to_bytes(4, "big"))
        for sequence in inputs:
            encoded = str(sequence.sequence).encode()
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return f"{base_group_id}:batch-{digest.hexdigest()}"


def _trace_row(
    *,
    inputs: tuple[ProtoSequence, ...],
    output: ConstraintOutput | None,
    recorded_at: str,
    run_id: str,
    group_id: str,
    collection_id: str | None,
    program_id: str | None,
    methodology_id: str | None,
    tier: str | None,
    program_seed: int | None,
    program_sha256: str,
    optimizer_index: int,
    constraint_label: str,
    constraint_identity: str,
    constraint_config: Any,
    constraint_threshold: float | None,
    constraint_weight: float,
    call_index: int,
    proposal_index: int,
    include_inputs: bool,
    latency: float,
    error: str | None,
) -> TraceRow:
    sequences = tuple(str(item.sequence) for item in inputs)
    return TraceRow(
        schema_version="1.1",
        constraint_config_scope="pre_run_contract",
        recorded_at=recorded_at,
        run_id=run_id,
        group_id=group_id,
        collection_id=collection_id,
        program_id=program_id,
        methodology_id=methodology_id,
        tier=tier,
        program_seed=program_seed,
        program_sha256=program_sha256,
        optimizer_index=optimizer_index,
        constraint_label=constraint_label,
        constraint_identity=constraint_identity,
        constraint_config=constraint_config,
        constraint_threshold=constraint_threshold,
        constraint_weight=constraint_weight,
        call_index=call_index,
        proposal_index=proposal_index,
        input_sha256=tuple(sha256(text.encode()).hexdigest() for text in sequences),
        input_sequences=sequences if include_inputs else None,
        input_structure_sha256=tuple(_structure_hash(item) for item in inputs),
        score=float(output.score) if output is not None else None,
        metadata=stable_data(output.metadata) if output is not None else None,
        has_structures=bool(output.structures) if output is not None else False,
        has_logits=bool(output.logits) if output is not None else False,
        call_latency_seconds=latency,
        error=error,
    )
