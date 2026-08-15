"""Finalize Phillip-generated Proto source as a validated collection."""

from __future__ import annotations

import ast
from pathlib import Path

from protofuse.program_collection import ProgramCollection, write_collection_manifest


def finalize_collection(
    collection_dir: Path,
    *,
    collection_id: str,
    methodology_id: str,
    proto_version: str,
    registry_version: str,
    seed_policy: str,
    reviewed: bool,
) -> ProgramCollection:
    """Validate builder declarations and generate `collection.json` without imports."""

    program_paths = sorted(collection_dir.glob("design_*.py"))
    if not program_paths:
        raise ValueError("collection contains no design_*.py programs")
    for path in program_paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        builders = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_program"
        ]
        if len(builders) != 1 or isinstance(builders[0], ast.AsyncFunctionDef):
            raise ValueError(f"program must define one synchronous build_program(): {path.name}")
    return write_collection_manifest(
        collection_dir,
        program_paths,
        collection_id=collection_id,
        methodology_id=methodology_id,
        proto_version=proto_version,
        registry_version=registry_version,
        seed_policy=seed_policy,
        reviewed=reviewed,
    )
