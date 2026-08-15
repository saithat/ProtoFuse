from pathlib import Path

import pytest

from protofuse.phillip import finalize_collection
from protofuse.program_collection import load_collection


def test_finalized_collection_verifies_without_importing(tmp_path: Path) -> None:
    program = tmp_path / "design_001.py"
    program.write_text("def build_program():\n    return object()\n")

    manifest = finalize_collection(
        tmp_path,
        collection_id="paper-1",
        methodology_id="method-1",
        proto_version="pinned-test-version",
        registry_version="1",
        seed_policy="caller supplied",
        reviewed=True,
    )
    loaded = load_collection(tmp_path)

    assert manifest == loaded.manifest
    assert loaded.program_paths == (program.resolve(),)


def test_collection_rejects_changed_program(tmp_path: Path) -> None:
    program = tmp_path / "design_001.py"
    program.write_text("def build_program():\n    return object()\n")
    finalize_collection(
        tmp_path,
        collection_id="paper-1",
        methodology_id="method-1",
        proto_version="pinned-test-version",
        registry_version="1",
        seed_policy="caller supplied",
        reviewed=True,
    )
    program.write_text("def build_program():\n    return None\n")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_collection(tmp_path)
