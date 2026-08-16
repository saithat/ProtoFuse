"""Crash-safe checkpoints for long-running Proto programs.

Checkpoints are JSON rather than pickle so they can be inspected without executing code.
They are written after every completed optimizer unit and restored fail-closed only when
the rebuilt program fingerprint matches the saved program.
"""

from __future__ import annotations

import inspect
import json
import math
import os
import re
from collections.abc import Callable, Iterator, Mapping
from collections.abc import Sequence as SequenceABC
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter
from types import MethodType
from typing import Any, Literal, cast

from proto_language.core import Program, Sequence
from proto_language.optimizer import (
    CyclingOptimizer,
    MCMCOptimizer,
    RejectionSamplingOptimizer,
)
from pydantic import BaseModel

CheckpointDevice = Literal["modal"] | None
CHECKPOINT_SCHEMA_VERSION = "1.0"
_SECRET_PATTERN = re.compile(r"(?i)\b(token|api[_-]?key|secret|authorization)\b\s*[:=]\s*[^\s,;]+")


class CheckpointCompatibilityError(RuntimeError):
    """Raised when saved state cannot safely be applied to a rebuilt program."""


@dataclass(frozen=True)
class CheckpointLocation:
    """Resolved location and identity for one resumable pipeline run."""

    root: Path
    run_id: str
    tier: str

    @property
    def directory(self) -> Path:
        return self.root / self.run_id / self.tier


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _redact_failure(message: str) -> str:
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[redacted]", message)[:1000]


def _encode_json(value: Any) -> Any:
    """Convert values to strict JSON while preserving non-finite floats."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"__protofuse_float__": "nan"}
        if math.isinf(value):
            return {"__protofuse_float__": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _encode_json(child) for key, child in value.items()}
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes, bytearray)):
        return [_encode_json(child) for child in value]
    item = getattr(value, "item", None)
    if callable(item):
        return _encode_json(item())
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _encode_json(tolist())
    raise TypeError(f"checkpoint contains non-JSON value {type(value).__name__}")


def _decode_json(value: Any) -> Any:
    if isinstance(value, dict):
        special = value.get("__protofuse_float__")
        if special == "nan":
            return float("nan")
        if special == "inf":
            return float("inf")
        if special == "-inf":
            return float("-inf")
        return {key: _decode_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_decode_json(child) for child in value]
    return value


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(_encode_json(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    loaded = _decode_json(json.loads(path.read_text()))
    if not isinstance(loaded, dict):
        raise CheckpointCompatibilityError(f"checkpoint root must be an object: {path}")
    return cast(dict[str, Any], loaded)


def _deep_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_deep_tuple(child) for child in value)
    if isinstance(value, dict):
        return {key: _deep_tuple(child) for key, child in value.items()}
    return value


def _stable_value(value: Any) -> Any:
    """Produce a deterministic, credential-free value for program fingerprints."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return _encode_json(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return _stable_value(value.model_dump(mode="json", exclude_none=False))
    if is_dataclass(value) and not isinstance(value, type):
        return _stable_value(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _stable_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes, bytearray)):
        return [_stable_value(child) for child in value]
    return {"type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _callable_fingerprint(value: Any) -> dict[str, Any] | None:
    if not callable(value):
        return None
    identity = f"{getattr(value, '__module__', '')}.{getattr(value, '__qualname__', '')}"
    try:
        source = inspect.getsource(value)
    except (OSError, TypeError):
        source = None
    return {
        "identity": identity,
        "source_sha256": sha256(source.encode()).hexdigest() if source else None,
    }


def _methodology_hash(run_id: str) -> str | None:
    repository_root = Path(__file__).resolve().parents[2]
    path = repository_root / "workspaces" / "phillip" / "fixtures" / run_id / "methodology.json"
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _program_fingerprint(program: Program, *, run_id: str, tier: str, index: int) -> str:
    optimizers: list[dict[str, Any]] = []
    for optimizer in program.optimizers:
        optimizer_data: Any = optimizer
        generators = []
        for generator in optimizer.generators:
            generator_data: Any = generator
            generators.append(
                {
                    "type": f"{type(generator).__module__}.{type(generator).__qualname__}",
                    "config": _stable_value(getattr(generator_data, "config", None)),
                }
            )
        constraints = []
        for constraint in optimizer.constraints:
            constraint_data: Any = constraint
            function = getattr(constraint_data, "_function", None)
            constraints.append(
                {
                    "label": constraint.label,
                    "threshold": constraint.threshold,
                    "weight": constraint.weight,
                    "function": (
                        f"{function.__module__}.{function.__qualname__}"
                        if callable(function)
                        else None
                    ),
                    "function_fingerprint": _callable_fingerprint(function),
                    "config": _stable_value(getattr(constraint_data, "_function_config", None)),
                }
            )
        segments = [
            {
                "label": segment.label,
                "sequence": segment.original_sequence.sequence,
                "sequence_type": segment.original_sequence.sequence_type,
            }
            for segment in optimizer.segments
        ]
        optimizers.append(
            {
                "type": f"{type(optimizer).__module__}.{type(optimizer).__qualname__}",
                "config": _stable_value(getattr(optimizer_data, "config", None)),
                "generators": generators,
                "constraints": constraints,
                "segments": segments,
                "conditioning_fn": _callable_fingerprint(
                    getattr(optimizer_data, "conditioning_fn", None)
                ),
            }
        )
    payload = {
        "schema": CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "tier": tier,
        "program_index": index,
        "methodology_sha256": _methodology_hash(run_id),
        "proto_language_version": _package_version("proto-language"),
        "program_seed": program.seed,
        "num_results": program.num_results,
        "optimizers": optimizers,
    }
    encoded = json.dumps(_encode_json(payload), sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _capture_seed_offsets(value: Any) -> list[dict[str, Any]]:
    offsets: list[dict[str, Any]] = []
    seen: set[int] = set()

    def visit(node: Any, path: list[str | int]) -> None:
        if node is None or isinstance(node, (str, bytes, bytearray, bool, int, float)):
            return
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        if hasattr(node, "_evaluation_seed_offset"):
            offset = node._evaluation_seed_offset
            if isinstance(offset, int):
                offsets.append({"path": path, "value": offset})
        if isinstance(node, BaseModel):
            for name in node.__class__.model_fields:
                visit(getattr(node, name), [*path, name])
        elif isinstance(node, Mapping):
            for key, child in node.items():
                visit(child, [*path, str(key)])
        elif isinstance(node, SequenceABC) and not isinstance(node, (str, bytes, bytearray)):
            for position, child in enumerate(node):
                visit(child, [*path, position])

    visit(value, [])
    return offsets


def _restore_seed_offsets(root: Any, offsets: list[dict[str, Any]]) -> None:
    for item in offsets:
        node = root
        path = item.get("path", [])
        if not isinstance(path, list):
            continue
        try:
            for part in path:
                if isinstance(part, int) or isinstance(node, Mapping):
                    node = node[part]
                else:
                    node = getattr(node, part)
            node._evaluation_seed_offset = int(item["value"])
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            continue


def _capture_optimizer_state(optimizer: Any) -> dict[str, Any]:
    generator_rng: list[Any] = []
    for generator in optimizer.generators:
        rng = getattr(generator, "_rng", None)
        generator_rng.append(rng.getstate() if rng is not None else None)

    constraint_offsets = []
    for constraint in optimizer.constraints:
        constraint_data: Any = constraint
        constraint_offsets.append(
            {
                "function": _capture_seed_offsets(
                    getattr(constraint_data, "_function_config", None)
                ),
                "backward": _capture_seed_offsets(
                    getattr(constraint_data, "_backward_config", None)
                ),
            }
        )

    state: dict[str, Any] = {
        "segments": [
            {
                "label": segment.label,
                "result": [
                    sequence.to_dict(include_logits=True, include_structure=True)
                    for sequence in segment.result_sequences
                ],
                "proposals": [
                    sequence.to_dict(include_logits=True, include_structure=True)
                    for sequence in segment.proposal_sequences
                ],
            }
            for segment in optimizer.segments
        ],
        "energy_scores": list(optimizer.energy_scores),
        "proposal_outcomes": list(getattr(optimizer, "_proposal_outcomes", [])),
        "proposal_energy_scores": list(getattr(optimizer, "_proposal_energy_scores", [])),
        "initial_state": getattr(optimizer, "_initial_state", None),
        "rng": {
            "optimizer": optimizer._rng.getstate(),
            "generators": generator_rng,
            "constraint_offsets": constraint_offsets,
        },
    }
    if isinstance(optimizer, RejectionSamplingOptimizer):
        state["result_energies"] = list(optimizer._result_energies)
        state["last_saved_proposal_number"] = optimizer._last_saved_proposal_number
    return state


def _restore_sequence_state(optimizer: Any, state: dict[str, Any]) -> None:
    segment_states = state.get("segments")
    if not isinstance(segment_states, list) or len(segment_states) != len(optimizer.segments):
        raise CheckpointCompatibilityError("checkpoint segment count does not match program")
    for segment, segment_state in zip(optimizer.segments, segment_states, strict=True):
        if not isinstance(segment_state, dict):
            raise CheckpointCompatibilityError("checkpoint segment state is invalid")
        saved_label = segment_state.get("label")
        if saved_label != segment.label:
            raise CheckpointCompatibilityError(
                f"checkpoint segment label {saved_label!r} does not match {segment.label!r}"
            )
        results = segment_state.get("result", [])
        proposals = segment_state.get("proposals", [])
        if not isinstance(results, list) or not isinstance(proposals, list):
            raise CheckpointCompatibilityError("checkpoint sequence pools are invalid")
        segment.result_sequences = [Sequence.from_dict(item) for item in results]
        segment.proposal_sequences = [Sequence.from_dict(item) for item in proposals]
    optimizer.energy_scores = [float(value) for value in state.get("energy_scores", [])]
    optimizer._proposal_outcomes = [str(value) for value in state.get("proposal_outcomes", [])]
    optimizer._proposal_energy_scores = [
        float(value) for value in state.get("proposal_energy_scores", [])
    ]
    if isinstance(optimizer, RejectionSamplingOptimizer):
        optimizer._result_energies = [float(value) for value in state.get("result_energies", [])]
        saved = state.get("last_saved_proposal_number")
        optimizer._last_saved_proposal_number = int(saved) if saved is not None else None


def _state_as_initial_state(state: dict[str, Any]) -> dict[str, Any]:
    segments = state.get("segments", [])
    return {
        "segments": [
            {
                "result": segment["result"],
                "proposals": segment["proposals"],
            }
            for segment in segments
        ],
        "energy_scores": list(state.get("energy_scores", [])),
    }


def _restore_rng_state(optimizer: Any, state: dict[str, Any]) -> None:
    rng_state = state.get("rng", {})
    if not isinstance(rng_state, dict):
        return
    optimizer_state = rng_state.get("optimizer")
    if optimizer_state is not None:
        optimizer._rng.setstate(_deep_tuple(optimizer_state))
    generator_states = rng_state.get("generators", [])
    if isinstance(generator_states, list):
        for generator, saved in zip(optimizer.generators, generator_states, strict=False):
            rng = getattr(generator, "_rng", None)
            if rng is not None and saved is not None:
                rng.setstate(_deep_tuple(saved))
    constraint_offsets = rng_state.get("constraint_offsets", [])
    if isinstance(constraint_offsets, list):
        for constraint, saved in zip(optimizer.constraints, constraint_offsets, strict=False):
            if not isinstance(saved, dict):
                continue
            constraint_data: Any = constraint
            function_offsets = saved.get("function", [])
            backward_offsets = saved.get("backward", [])
            if isinstance(function_offsets, list):
                _restore_seed_offsets(
                    getattr(constraint_data, "_function_config", None),
                    function_offsets,
                )
            if isinstance(backward_offsets, list):
                _restore_seed_offsets(
                    getattr(constraint_data, "_backward_config", None),
                    backward_offsets,
                )


def _planned_units(optimizer: Any) -> int:
    if isinstance(optimizer, RejectionSamplingOptimizer):
        return int(optimizer.num_samples)
    return int(optimizer.num_steps)


def _optimizer_kind(optimizer: Any) -> str:
    if isinstance(optimizer, MCMCOptimizer):
        return "mcmc"
    if isinstance(optimizer, CyclingOptimizer):
        return "cycling"
    if isinstance(optimizer, RejectionSamplingOptimizer):
        return "rejection-sampling"
    return f"unsupported:{type(optimizer).__module__}.{type(optimizer).__qualname__}"


class CheckpointSession:
    """Coordinate checkpoints across every Program invoked by one pipeline command."""

    def __init__(
        self,
        location: CheckpointLocation,
        *,
        restart: bool = False,
    ) -> None:
        self.location = location
        self.restart = restart
        self._program_index = 0
        self._manifest: dict[str, Any] = {}
        self._attempt_started = 0.0
        self._attempt_index = 0

    @property
    def directory(self) -> Path:
        return self.location.directory

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    def __enter__(self) -> CheckpointSession:
        if self.restart and self.directory.exists():
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            archive = self.directory.with_name(f"{self.directory.name}.archived-{timestamp}")
            self.directory.rename(archive)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.is_file():
            self._manifest = _read_json(self.manifest_path)
            self._validate_manifest()
        else:
            self._manifest = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "run_id": self.location.run_id,
                "tier": self.location.tier,
                "status": "running",
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "program_count": 0,
                "failure": None,
            }
            self._save_manifest()
        self._manifest["status"] = "running"
        self._manifest["failure"] = None
        attempts = self._manifest.setdefault("attempts", [])
        if not isinstance(attempts, list):
            raise CheckpointCompatibilityError("checkpoint attempts must be an array")
        self._attempt_index = len(attempts)
        attempts.append(
            {
                "attempt": self._attempt_index + 1,
                "status": "running",
                "started_at": _utc_now(),
            }
        )
        self._manifest["resume_count"] = self._attempt_index
        self._attempt_started = perf_counter()
        self._save_manifest()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: Any,
    ) -> Literal[False]:
        del exception_type, traceback
        if exception is None:
            self._manifest["status"] = "completed"
            self._manifest["completed_at"] = _utc_now()
            self._manifest["failure"] = None
        else:
            self._manifest["status"] = "interrupted"
            self._manifest["failure"] = {
                "type": type(exception).__name__,
                "message": _redact_failure(str(exception)),
            }
        attempts = self._manifest.get("attempts", [])
        if isinstance(attempts, list) and len(attempts) > self._attempt_index:
            attempt = attempts[self._attempt_index]
            if isinstance(attempt, dict):
                attempt["status"] = self._manifest["status"]
                attempt["ended_at"] = _utc_now()
                attempt["wall_time_seconds"] = perf_counter() - self._attempt_started
                attempt["failure"] = self._manifest["failure"]
            self._manifest["cumulative_wall_time_seconds"] = sum(
                float(item.get("wall_time_seconds", 0.0))
                for item in attempts
                if isinstance(item, dict)
            )
        self._save_manifest()
        return False

    def _validate_manifest(self) -> None:
        expected = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "run_id": self.location.run_id,
            "tier": self.location.tier,
        }
        for field, value in expected.items():
            if self._manifest.get(field) != value:
                raise CheckpointCompatibilityError(
                    f"checkpoint {field}={self._manifest.get(field)!r} does not match {value!r}; "
                    "use --restart to archive it and start a new run"
                )

    def _save_manifest(self) -> None:
        self._manifest["updated_at"] = _utc_now()
        _atomic_write_json(self.manifest_path, self._manifest)

    def _program_path(self, index: int) -> Path:
        return self.directory / f"program-{index:04d}.json"

    def _trace_path(self, index: int) -> Path:
        return self.directory / f"program-{index:04d}.trace.jsonl"

    def _save_program(self, path: Path, record: dict[str, Any]) -> None:
        record["updated_at"] = _utc_now()
        _atomic_write_json(path, record)

    def _append_trace(
        self,
        *,
        index: int,
        stage_index: int,
        completed_units: int,
        optimizer: Any,
    ) -> None:
        sequence_hashes = [
            sha256(sequence.sequence.encode()).hexdigest()
            for segment in optimizer.segments
            for sequence in segment.result_sequences
        ]
        trace = {
            "recorded_at": _utc_now(),
            "run_id": self.location.run_id,
            "tier": self.location.tier,
            "program_index": index,
            "stage_index": stage_index,
            "optimizer": _optimizer_kind(optimizer),
            "completed_units": completed_units,
            "energy_scores": list(optimizer.energy_scores),
            "result_sequence_sha256": sequence_hashes,
        }
        path = self._trace_path(index)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_encode_json(trace), sort_keys=True, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def run_program(self, program: Program, *, device: CheckpointDevice = None) -> None:
        program.current_stage = 0
        program._stage_results = []
        index = self._program_index
        self._program_index += 1
        self._manifest["program_count"] = max(
            int(self._manifest.get("program_count", 0)), self._program_index
        )
        self._manifest["current_program"] = index
        self._save_manifest()

        path = self._program_path(index)
        fingerprint = _program_fingerprint(
            program,
            run_id=self.location.run_id,
            tier=self.location.tier,
            index=index,
        )
        if path.is_file():
            record = _read_json(path)
            if record.get("fingerprint") != fingerprint:
                raise CheckpointCompatibilityError(
                    f"program {index} no longer matches its checkpoint; use --restart to "
                    "archive the old run before executing changed code"
                )
        else:
            record = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "run_id": self.location.run_id,
                "tier": self.location.tier,
                "program_index": index,
                "fingerprint": fingerprint,
                "status": "running",
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "failure": None,
                "stages": {},
            }

        if record.get("status") == "completed":
            self._restore_completed_program(program, record)
            return

        stages = record.setdefault("stages", {})
        if not isinstance(stages, dict):
            raise CheckpointCompatibilityError("checkpoint stages must be an object")

        try:
            for stage_index, optimizer in enumerate(program.optimizers):
                stage_key = str(stage_index)
                stage_record = stages.get(stage_key)
                if isinstance(stage_record, dict) and stage_record.get("status") == "completed":
                    state = stage_record.get("state")
                    if not isinstance(state, dict):
                        raise CheckpointCompatibilityError("completed stage has no state")
                    _restore_sequence_state(optimizer, state)
                    program._stage_results.append(program.extract_results(optimizer.energy_scores))
                    program.current_stage = stage_index + 1
                    continue
                self._run_stage(
                    program,
                    optimizer=optimizer,
                    stage_index=stage_index,
                    index=index,
                    path=path,
                    record=record,
                    device=device,
                )
            record["status"] = "completed"
            record["completed_at"] = _utc_now()
            record["failure"] = None
            self._save_program(path, record)
        except BaseException as exc:
            record["status"] = "interrupted"
            record["failure"] = {
                "type": type(exc).__name__,
                "message": _redact_failure(str(exc)),
            }
            self._save_program(path, record)
            raise

    def _restore_completed_program(self, program: Program, record: dict[str, Any]) -> None:
        stages = record.get("stages")
        if not isinstance(stages, dict):
            raise CheckpointCompatibilityError("completed checkpoint has no stages")
        for stage_index, optimizer in enumerate(program.optimizers):
            stage = stages.get(str(stage_index))
            if not isinstance(stage, dict) or stage.get("status") != "completed":
                raise CheckpointCompatibilityError("completed checkpoint has an incomplete stage")
            state = stage.get("state")
            if not isinstance(state, dict):
                raise CheckpointCompatibilityError("completed checkpoint stage has no state")
            _restore_sequence_state(optimizer, state)
            program._stage_results.append(program.extract_results(optimizer.energy_scores))
        program.current_stage = len(program.optimizers)

    def _run_stage(
        self,
        program: Program,
        *,
        optimizer: Any,
        stage_index: int,
        index: int,
        path: Path,
        record: dict[str, Any],
        device: CheckpointDevice,
    ) -> None:
        stages = cast(dict[str, Any], record["stages"])
        stage_key = str(stage_index)
        saved = stages.get(stage_key)
        planned_units = _planned_units(optimizer)
        if saved is None:
            stage_record: dict[str, Any] = {
                "status": "running",
                "optimizer": _optimizer_kind(optimizer),
                "planned_units": planned_units,
                "completed_units": 0,
                "state": _capture_optimizer_state(optimizer),
                "started_at": _utc_now(),
            }
            stages[stage_key] = stage_record
            self._save_program(path, record)
        elif isinstance(saved, dict):
            stage_record = saved
            if stage_record.get("optimizer") != _optimizer_kind(optimizer):
                raise CheckpointCompatibilityError("checkpoint optimizer type changed")
            if int(stage_record.get("planned_units", -1)) != planned_units:
                raise CheckpointCompatibilityError("checkpoint optimizer unit count changed")
        else:
            raise CheckpointCompatibilityError("checkpoint stage record is invalid")

        completed_units = int(stage_record.get("completed_units", 0))
        saved_state = stage_record.get("state")
        if not isinstance(saved_state, dict):
            raise CheckpointCompatibilityError("checkpoint stage state is invalid")

        # The final optimizer callback runs before Program.run_stage extracts and
        # records results. If that small finalization window was interrupted, do
        # not repeat the final (potentially paid) optimizer unit.
        if completed_units >= planned_units:
            _restore_sequence_state(optimizer, saved_state)
            stage_result = program.extract_results(optimizer.energy_scores)
            program._stage_results.append(stage_result)
            program.current_stage = stage_index + 1
            stage_record["status"] = "completed"
            stage_record["completed_at"] = _utc_now()
            self._save_program(path, record)
            return

        cleanup: list[Callable[[], None]] = []
        absolute_steps = False
        if completed_units > 0:
            resume_events = stage_record.setdefault("resume_events", [])
            if isinstance(resume_events, list):
                resume_events.append(
                    {
                        "resumed_at": _utc_now(),
                        "completed_units": completed_units,
                    }
                )
            if isinstance(optimizer, MCMCOptimizer):
                cleanup.extend(
                    self._prepare_mcmc_resume(
                        optimizer,
                        state=saved_state,
                        completed_units=completed_units,
                        planned_units=planned_units,
                    )
                )
            elif isinstance(optimizer, CyclingOptimizer):
                cleanup.extend(
                    self._prepare_cycling_resume(
                        optimizer,
                        state=saved_state,
                        completed_units=completed_units,
                        planned_units=planned_units,
                    )
                )
            elif isinstance(optimizer, RejectionSamplingOptimizer):
                cleanup.extend(
                    self._prepare_rejection_resume(
                        optimizer,
                        state=saved_state,
                        completed_units=completed_units,
                        planned_units=planned_units,
                    )
                )
                absolute_steps = True
            else:
                raise CheckpointCompatibilityError(
                    f"{_optimizer_kind(optimizer)} cannot safely resume mid-stage"
                )

        previous_logging = optimizer.custom_logging
        previous_interval = optimizer.tracking_interval
        previous_config_interval = optimizer.config.tracking_interval
        optimizer.tracking_interval = 1
        optimizer.config.tracking_interval = 1

        def checkpoint_callback(step: int, segments: Any) -> None:
            del segments
            global_step = step if absolute_steps else completed_units + step
            if (
                isinstance(optimizer, RejectionSamplingOptimizer)
                and global_step < planned_units
                and global_step % optimizer.proposal_batch_size != 0
            ):
                if previous_logging is not None:
                    previous_logging(global_step, optimizer.segments)
                return
            stage_record["completed_units"] = global_step
            stage_record["state"] = _capture_optimizer_state(optimizer)
            stage_record["status"] = "running"
            stage_record["last_checkpoint_at"] = _utc_now()
            record["status"] = "running"
            record["failure"] = None
            self._save_program(path, record)
            self._append_trace(
                index=index,
                stage_index=stage_index,
                completed_units=global_step,
                optimizer=optimizer,
            )
            if previous_logging is not None:
                previous_logging(global_step, optimizer.segments)

        optimizer.custom_logging = checkpoint_callback
        try:
            program.current_stage = stage_index
            program.run_stage(stage_index, device=device)
            stage_record["status"] = "completed"
            stage_record["state"] = _capture_optimizer_state(optimizer)
            stage_record["completed_at"] = _utc_now()
            if int(stage_record.get("completed_units", 0)) == 0:
                stage_record["completed_units"] = planned_units
            self._save_program(path, record)
        finally:
            optimizer.custom_logging = previous_logging
            optimizer.tracking_interval = previous_interval
            optimizer.config.tracking_interval = previous_config_interval
            for restore in reversed(cleanup):
                restore()

    @staticmethod
    def _patch_rng_reset(optimizer: Any, state: dict[str, Any]) -> Callable[[], None]:
        original = optimizer._reset_seed_state

        def reset_with_checkpoint(self: Any) -> None:
            original()
            _restore_rng_state(self, state)

        optimizer._reset_seed_state = MethodType(reset_with_checkpoint, optimizer)

        def restore() -> None:
            optimizer._reset_seed_state = original

        return restore

    def _prepare_mcmc_resume(
        self,
        optimizer: MCMCOptimizer,
        *,
        state: dict[str, Any],
        completed_units: int,
        planned_units: int,
    ) -> list[Callable[[], None]]:
        _restore_sequence_state(optimizer, state)
        remaining = planned_units - completed_units
        if remaining < 1:
            raise CheckpointCompatibilityError("MCMC checkpoint has no remaining steps")
        optimizer_data: Any = optimizer
        optimizer._initial_state = _state_as_initial_state(state)

        original_steps = optimizer.num_steps
        original_config_steps = optimizer.config.num_steps
        original_schedule = optimizer_data._temperature_schedule
        original_score = optimizer.score_energy
        optimizer.num_steps = remaining
        optimizer.config.num_steps = remaining

        def shifted_schedule(step: int, total: int) -> float:
            del total
            return float(original_schedule(completed_units + step, planned_units))

        optimizer_data._temperature_schedule = shifted_schedule
        skip_initial_score = True

        def score_after_resume(*args: Any, **kwargs: Any) -> None:
            nonlocal skip_initial_score
            if skip_initial_score:
                skip_initial_score = False
                return
            original_score(*args, **kwargs)

        optimizer_data.score_energy = score_after_resume
        cleanup = [self._patch_rng_reset(optimizer, state)]

        def restore() -> None:
            optimizer.num_steps = original_steps
            optimizer.config.num_steps = original_config_steps
            optimizer_data._temperature_schedule = original_schedule
            optimizer_data.score_energy = original_score

        cleanup.append(restore)
        return cleanup

    def _prepare_cycling_resume(
        self,
        optimizer: CyclingOptimizer,
        *,
        state: dict[str, Any],
        completed_units: int,
        planned_units: int,
    ) -> list[Callable[[], None]]:
        _restore_sequence_state(optimizer, state)
        remaining = planned_units - completed_units
        if remaining < 1:
            raise CheckpointCompatibilityError("cycling checkpoint has no remaining steps")
        original_steps = optimizer.num_steps
        original_config_steps = optimizer.config.num_steps
        optimizer.num_steps = remaining
        optimizer.config.num_steps = remaining
        optimizer._initial_state = _state_as_initial_state(state)
        cleanup = [self._patch_rng_reset(optimizer, state)]

        def restore() -> None:
            optimizer.num_steps = original_steps
            optimizer.config.num_steps = original_config_steps

        cleanup.append(restore)
        return cleanup

    def _prepare_rejection_resume(
        self,
        optimizer: RejectionSamplingOptimizer,
        *,
        state: dict[str, Any],
        completed_units: int,
        planned_units: int,
    ) -> list[Callable[[], None]]:
        if optimizer.config.proposal_source == "existing_results":
            raise CheckpointCompatibilityError(
                "existing-results rejection sampling cannot safely resume mid-stage"
            )
        initial_state = state.get("initial_state")
        if not isinstance(initial_state, dict):
            raise CheckpointCompatibilityError("rejection checkpoint has no original state")
        _restore_sequence_state(optimizer, state)
        optimizer._initial_state = initial_state
        optimizer_data: Any = optimizer

        original_restore = optimizer_data._restore_initial_state
        original_run = optimizer_data.run
        checkpoint_results = state

        def restore_with_checkpoint(self: Any) -> None:
            initial = self._initial_state
            if not isinstance(initial, dict):
                raise CheckpointCompatibilityError("rejection checkpoint initial state is invalid")
            for position, segment in enumerate(self.segments):
                initial_segment = initial["segments"][position]
                segment.proposal_sequences = [
                    Sequence.from_dict(item) for item in initial_segment["proposals"]
                ]
            _restore_sequence_state(self, checkpoint_results)
            self.history = []

        optimizer_data._restore_initial_state = MethodType(restore_with_checkpoint, optimizer)

        def resume_rejection(self: Any) -> None:
            self._prepare_run()
            proposals_generated = completed_units
            batch_num = proposals_generated // self.proposal_batch_size + 1
            threshold_met = False
            while proposals_generated < planned_units:
                batch_size = min(self.proposal_batch_size, planned_units - proposals_generated)
                proposals_generated = self._run_proposal_batch(
                    batch_num,
                    proposals_generated + 1,
                    batch_size,
                )
                if (
                    self.energy_threshold is not None
                    and len(self._result_energies) == self.num_results
                    and self._result_energies[-1] < self.energy_threshold
                ):
                    threshold_met = True
                    break
                batch_num += 1
            if not threshold_met and self._last_saved_proposal_number != proposals_generated:
                self._save_proposal_snapshot(
                    proposals_generated,
                    max(batch_num - 1, 1),
                    max(batch_size - 1, 0),
                )
            self.energy_scores = list(self._result_energies)

        optimizer_data.run = MethodType(resume_rejection, optimizer)
        cleanup = [self._patch_rng_reset(optimizer, state)]

        def restore() -> None:
            optimizer_data._restore_initial_state = original_restore
            optimizer_data.run = original_run

        cleanup.append(restore)
        return cleanup


_ACTIVE_CHECKPOINT_SESSION: ContextVar[CheckpointSession | None] = ContextVar(
    "protofuse_checkpoint_session", default=None
)


@contextmanager
def checkpoint_session(
    root: Path | str,
    *,
    run_id: str,
    tier: str,
    restart: bool = False,
) -> Iterator[CheckpointSession]:
    """Activate checkpointing for every nested pipeline Program execution."""

    session = CheckpointSession(
        CheckpointLocation(root=Path(root), run_id=run_id, tier=tier),
        restart=restart,
    )
    token = _ACTIVE_CHECKPOINT_SESSION.set(session)
    try:
        with session:
            yield session
    finally:
        _ACTIVE_CHECKPOINT_SESSION.reset(token)


def run_program(program: Program, *, device: CheckpointDevice = None) -> None:
    """Run through the active checkpoint session, or use ordinary Proto execution."""

    session = _ACTIVE_CHECKPOINT_SESSION.get()
    if session is None:
        program.run(device=device)
        return
    session.run_program(program, device=device)


def run_with_checkpoints(
    program: Program,
    *,
    checkpoint_dir: Path | str,
    run_id: str,
    tier: str = "custom",
    restart: bool = False,
    device: CheckpointDevice = None,
) -> Program:
    """Execute an ordinary or fused Proto Program with automatic resume support."""

    with checkpoint_session(
        checkpoint_dir,
        run_id=run_id,
        tier=tier,
        restart=restart,
    ):
        run_program(program, device=device)
    return program
