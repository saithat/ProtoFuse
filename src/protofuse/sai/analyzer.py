"""Controlled loading and structural analysis of reviewed Proto collections."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from proto_language.core import Program

from protofuse.phillip.generator import validate_program_source
from protofuse.program_collection import ProgramEntry, ValidatedCollection, load_collection
from protofuse.sai.signatures import ProgramSignature, program_signature


@dataclass(frozen=True)
class LoadedReviewedProgram:
    collection: ValidatedCollection
    entry: ProgramEntry
    program: Program
    signature: ProgramSignature


def _entry_for_id(collection: ValidatedCollection, program_id: str) -> ProgramEntry:
    matches = [entry for entry in collection.manifest.programs if entry.program_id == program_id]
    if len(matches) != 1:
        known = ", ".join(entry.program_id for entry in collection.manifest.programs)
        raise ValueError(f"unknown program_id {program_id!r}; expected one of: {known}")
    return matches[0]


def load_reviewed_program(collection_dir: Path, *, program_id: str) -> LoadedReviewedProgram:
    """Hash-check, source-check, import, and build one reviewed program."""

    collection = load_collection(collection_dir, require_reviewed=True)
    entry = _entry_for_id(collection, program_id)
    path = collection.root / entry.path
    validate_program_source(path.read_text(), filename=entry.path)

    module_name = f"protofuse_reviewed_{collection.manifest.collection_id}_{entry.program_id}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not construct import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_program = getattr(module, entry.entrypoint, None)
    if not callable(build_program):
        raise TypeError(f"{entry.path} entrypoint {entry.entrypoint!r} is not callable")
    program = build_program()
    if not isinstance(program, Program):
        raise TypeError(f"{entry.path} returned {type(program).__name__}, expected Program")
    return LoadedReviewedProgram(
        collection=collection,
        entry=entry,
        program=program,
        signature=program_signature(program),
    )
