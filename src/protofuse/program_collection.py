"""The single filesystem contract between Phillip's generator and Sai's analyzer."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CollectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProgramEntry(CollectionModel):
    program_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    path: str
    entrypoint: Literal["build_program"] = "build_program"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def path_is_relative_python(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
            raise ValueError("program path must be a relative Python file")
        return value


class ProgramCollection(CollectionModel):
    schema_version: Literal["1.0"] = "1.0"
    collection_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    methodology_id: str = Field(min_length=1)
    proto_version: str = Field(min_length=1)
    registry_version: str = Field(min_length=1)
    seed_policy: str = Field(min_length=1)
    reviewed: bool
    programs: list[ProgramEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def programs_are_unique(self) -> ProgramCollection:
        ids = [program.program_id for program in self.programs]
        paths = [program.path for program in self.programs]
        if len(ids) != len(set(ids)):
            raise ValueError("program IDs must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("program paths must be unique")
        return self


@dataclass(frozen=True)
class ValidatedCollection:
    root: Path
    manifest: ProgramCollection
    program_paths: tuple[Path, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_collection(
    collection_dir: Path,
    *,
    require_reviewed: bool = True,
) -> ValidatedCollection:
    """Validate a collection and its hashes without importing generated code."""

    root = collection_dir.resolve()
    manifest_path = root / "collection.json"
    manifest = ProgramCollection.model_validate_json(manifest_path.read_text())
    if require_reviewed and not manifest.reviewed:
        raise ValueError("collection is not reviewed")

    program_paths: list[Path] = []
    for entry in manifest.programs:
        unresolved = root / entry.path
        if unresolved.is_symlink():
            raise ValueError(f"program cannot be a symlink: {entry.path}")
        program_path = unresolved.resolve()
        if not program_path.is_relative_to(root) or not program_path.is_file():
            raise ValueError(f"program is outside the collection or missing: {entry.path}")
        if file_sha256(program_path) != entry.sha256:
            raise ValueError(f"program hash mismatch: {entry.path}")
        program_paths.append(program_path)

    return ValidatedCollection(root, manifest, tuple(program_paths))


def write_collection_manifest(
    collection_dir: Path,
    program_paths: Iterable[Path],
    *,
    collection_id: str,
    methodology_id: str,
    proto_version: str,
    registry_version: str,
    seed_policy: str,
    reviewed: bool,
) -> ProgramCollection:
    """Write the small manifest after Phillip has generated and reviewed program files."""

    root = collection_dir.resolve()
    entries: list[ProgramEntry] = []
    for path in sorted((program.resolve() for program in program_paths), key=str):
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"program is outside the collection or missing: {path}")
        entries.append(
            ProgramEntry(
                program_id=path.stem.replace("_", "-"),
                path=path.relative_to(root).as_posix(),
                sha256=file_sha256(path),
            )
        )
    manifest = ProgramCollection(
        collection_id=collection_id,
        methodology_id=methodology_id,
        proto_version=proto_version,
        registry_version=registry_version,
        seed_policy=seed_policy,
        reviewed=reviewed,
        programs=entries,
    )
    (root / "collection.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest
