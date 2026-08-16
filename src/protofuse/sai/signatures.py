"""Canonical, fail-closed signatures for real Proto program components."""

from __future__ import annotations

import dataclasses
import inspect
import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class SignatureModel(BaseModel):
    """Strict immutable base for compatibility signatures."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CallableSignature(SignatureModel):
    identity: str
    source_sha256: str | None


class InputRequirement(SignatureModel):
    label: str
    requires_logits: bool
    requires_structure: bool


class SegmentSignature(SignatureModel):
    key: str
    sequence_type: str
    length: int
    fixed_sequence_sha256: str | None


class GeneratorSignature(SignatureModel):
    implementation: str
    config: Any
    segment_keys: tuple[str, ...]


class ConstraintSignature(SignatureModel):
    label: str
    function: CallableSignature | None
    backward: CallableSignature | None
    function_config: Any
    backward_config: Any
    threshold: float | None
    weight: float
    input_segment_keys: tuple[str, ...]
    input_requirements: tuple[InputRequirement, ...]
    gradient_positions: tuple[int, ...] | None


class OptimizerSignature(SignatureModel):
    index: int
    implementation: str
    config: Any
    generators: tuple[GeneratorSignature, ...]
    constraints: tuple[ConstraintSignature, ...]


class ProgramSignature(SignatureModel):
    proto_language_version: str
    proto_tools_version: str
    num_results: int
    segments: tuple[SegmentSignature, ...]
    optimizers: tuple[OptimizerSignature, ...]

    @property
    def sha256(self) -> str:
        return signature_sha256(self)


class StepGroupSignature(SignatureModel):
    """Compatibility boundary for one replaceable constraint group."""

    proto_language_version: str
    proto_tools_version: str
    optimizer_index: int
    optimizer_implementation: str
    optimizer_config: Any
    generators: tuple[GeneratorSignature, ...]
    constraints: tuple[ConstraintSignature, ...]
    segments: tuple[SegmentSignature, ...]

    @property
    def sha256(self) -> str:
        return signature_sha256(self)


def _qualified_name(value: object) -> str:
    cls = value if isinstance(value, type) else type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def callable_signature(value: object | None) -> CallableSignature | None:
    if value is None or not callable(value):
        return None
    identity = f"{getattr(value, '__module__', '')}.{getattr(value, '__qualname__', '')}"
    try:
        source = inspect.getsource(value)
    except (OSError, TypeError):
        source = None
    return CallableSignature(
        identity=identity,
        source_sha256=sha256(source.encode()).hexdigest() if source else None,
    )


def stable_data(value: Any) -> Any:
    """Convert runtime configuration into deterministic JSON-safe data."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value:
            return {"float": "nan"}
        if value == float("inf"):
            return {"float": "inf"}
        if value == float("-inf"):
            return {"float": "-inf"}
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return stable_data(value.model_dump(mode="python", exclude_none=False))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return stable_data(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): stable_data(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [stable_data(child) for child in value]

    structure = getattr(value, "structure", None)
    if isinstance(structure, str):
        return {
            "type": _qualified_name(value),
            "structure_sha256": sha256(structure.encode()).hexdigest(),
        }

    tobytes = getattr(value, "tobytes", None)
    shape = getattr(value, "shape", None)
    if callable(tobytes) and shape is not None:
        try:
            payload = bytes(tobytes())
        except (TypeError, ValueError):
            pass
        else:
            return {
                "type": _qualified_name(value),
                "shape": stable_data(tuple(shape)),
                "sha256": sha256(payload).hexdigest(),
            }

    if callable(value):
        signature = callable_signature(value)
        return signature.model_dump(mode="json") if signature else None
    return {"type": _qualified_name(value)}


def signature_sha256(signature: SignatureModel) -> str:
    encoded = json.dumps(
        signature.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(encoded.encode()).hexdigest()


def _segment_context(program: Any) -> tuple[dict[int, str], set[int], tuple[SegmentSignature, ...]]:
    segment_keys: dict[int, str] = {}
    assigned: set[int] = set()
    for optimizer in program.optimizers:
        for generator in optimizer.generators:
            for segment in generator.segments:
                assigned.add(id(segment))

    signatures: list[SegmentSignature] = []
    for construct_index, construct in enumerate(program.constructs):
        for segment_index, segment in enumerate(construct.segments):
            key = f"{construct_index}:{segment_index}"
            segment_keys[id(segment)] = key
            sequence = segment.original_sequence
            sequence_text = str(sequence.sequence)
            signatures.append(
                SegmentSignature(
                    key=key,
                    sequence_type=str(sequence.sequence_type),
                    length=len(sequence_text) if sequence_text else int(segment.sequence_length),
                    fixed_sequence_sha256=(
                        sha256(sequence_text.encode()).hexdigest()
                        if id(segment) not in assigned and sequence_text
                        else None
                    ),
                )
            )
    return segment_keys, assigned, tuple(signatures)


def _generator_signature(generator: Any, segment_keys: Mapping[int, str]) -> GeneratorSignature:
    return GeneratorSignature(
        implementation=_qualified_name(generator),
        config=stable_data(getattr(generator, "config", None)),
        segment_keys=tuple(segment_keys[id(segment)] for segment in generator.segments),
    )


def _constraint_signature(
    constraint: Any,
    segment_keys: Mapping[int, str],
) -> ConstraintSignature:
    slots = getattr(constraint, "_input_slots", ())
    return ConstraintSignature(
        label=str(constraint.label),
        function=callable_signature(constraint.function),
        backward=callable_signature(constraint.backward),
        function_config=stable_data(constraint.function_config),
        backward_config=stable_data(constraint.backward_config),
        threshold=constraint.threshold,
        weight=float(constraint.weight),
        input_segment_keys=tuple(segment_keys[id(segment)] for segment in constraint.inputs),
        input_requirements=tuple(
            InputRequirement(
                label=str(slot.label),
                requires_logits=bool(slot.requires_logits),
                requires_structure=bool(slot.requires_structure),
            )
            for slot in slots
        ),
        gradient_positions=constraint.gradient_positions,
    )


def program_signature(program: Any) -> ProgramSignature:
    segment_keys, _, segments = _segment_context(program)
    optimizers = tuple(
        OptimizerSignature(
            index=index,
            implementation=_qualified_name(optimizer),
            config=stable_data(getattr(optimizer, "config", None)),
            generators=tuple(
                _generator_signature(generator, segment_keys) for generator in optimizer.generators
            ),
            constraints=tuple(
                _constraint_signature(constraint, segment_keys)
                for constraint in optimizer.constraints
            ),
        )
        for index, optimizer in enumerate(program.optimizers)
    )
    return ProgramSignature(
        proto_language_version=_package_version("proto-language"),
        proto_tools_version=_package_version("proto-tools"),
        num_results=int(program.num_results),
        segments=segments,
        optimizers=optimizers,
    )


def step_group_signature(
    program: Any,
    *,
    optimizer_index: int,
    constraint_labels: Sequence[str],
) -> StepGroupSignature:
    """Create an exact signature for an ordered constraint group."""

    try:
        optimizer = program.optimizers[optimizer_index]
    except IndexError as exc:
        raise ValueError(f"optimizer index out of range: {optimizer_index}") from exc
    requested = tuple(constraint_labels)
    if not requested or len(requested) != len(set(requested)):
        raise ValueError("constraint_labels must be non-empty and unique")
    by_label = {str(constraint.label): constraint for constraint in optimizer.constraints}
    missing = [label for label in requested if label not in by_label]
    if missing:
        raise ValueError(f"constraints not found in optimizer {optimizer_index}: {missing}")

    segment_keys, _, all_segments = _segment_context(program)
    constraints = tuple(_constraint_signature(by_label[label], segment_keys) for label in requested)
    referenced = {key for constraint in constraints for key in constraint.input_segment_keys}
    segments = tuple(segment for segment in all_segments if segment.key in referenced)
    return StepGroupSignature(
        proto_language_version=_package_version("proto-language"),
        proto_tools_version=_package_version("proto-tools"),
        optimizer_index=optimizer_index,
        optimizer_implementation=_qualified_name(optimizer),
        optimizer_config=stable_data(getattr(optimizer, "config", None)),
        generators=tuple(
            _generator_signature(generator, segment_keys) for generator in optimizer.generators
        ),
        constraints=constraints,
        segments=segments,
    )
