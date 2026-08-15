from pathlib import Path

import pytest

from protofuse.phillip import finalize_collection
from protofuse.program_collection import load_collection

REPO_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COLLECTION = REPO_ROOT / "proto_programs/generated/custom-egfp-lung"

MINIMAL_PROGRAM = '''"""Minimal handoff program for collection tests."""

from __future__ import annotations

from proto_language.core import Program


def build_program() -> Program:
    raise NotImplementedError
'''


def test_finalized_collection_verifies_without_importing(tmp_path: Path) -> None:
    program = tmp_path / "design_001.py"
    program.write_text(MINIMAL_PROGRAM)

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
    program.write_text(MINIMAL_PROGRAM)
    finalize_collection(
        tmp_path,
        collection_id="paper-1",
        methodology_id="method-1",
        proto_version="pinned-test-version",
        registry_version="1",
        seed_policy="caller supplied",
        reviewed=True,
    )
    program.write_text(
        '"""Changed."""\n\nfrom __future__ import annotations\n\n'
        "from proto_language.core import Program\n\n\n"
        "def build_program() -> Program:\n    raise NotImplementedError\n"
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        load_collection(tmp_path)


def test_dnachisel_num1_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(
        REPO_ROOT / "proto_programs/generated/dnachisel-num1",
        require_reviewed=True,
    )

    assert loaded.manifest.collection_id == "dnachisel-num1"
    assert loaded.manifest.methodology_id == "dnachisel-v2"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2


def test_esm2_protein_maturation_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(
        REPO_ROOT / "proto_programs/generated/esm2-protein-maturation",
        require_reviewed=True,
    )

    assert loaded.manifest.collection_id == "esm2-protein-maturation"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2


def test_antibody_cdr_maturation_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(
        REPO_ROOT / "proto_programs/generated/antibody-cdr-maturation",
        require_reviewed=True,
    )

    assert loaded.manifest.collection_id == "antibody-cdr-maturation"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2


def test_custom_egfp_lung_collection_is_reviewed_and_hashed() -> None:
    loaded = load_collection(CUSTOM_COLLECTION, require_reviewed=True)

    assert loaded.manifest.collection_id == "custom-egfp-lung"
    assert loaded.manifest.methodology_id == "custom-egfp-v1"
    assert loaded.manifest.reviewed is True
    assert len(loaded.manifest.programs) == 2
    assert {entry.program_id for entry in loaded.manifest.programs} == {
        "design-001",
        "design-002",
    }


def test_custom_egfp_design_builds_program() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "custom_design_001",
        CUSTOM_COLLECTION / "design_001.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    program = module.build_program()
    assert program.constructs[0].segments[0].sequence_length == 720
