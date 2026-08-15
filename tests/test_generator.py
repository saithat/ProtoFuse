from pathlib import Path

import pytest

from protofuse.phillip import (
    UnresolvedBindingsError,
    compile_proto_plan,
    generate_program_sources,
    require_resolved_plan,
    validate_program_source,
)
from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.program_builders import load_fixture_spec
from protofuse.phillip.registries import lookup_registry, profile_for_fixture
from protofuse.phillip.topology import recommend_topologies

REPO_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COLLECTION = REPO_ROOT / "proto_programs/generated/custom-egfp-lung"
DNACHISEL_COLLECTION = REPO_ROOT / "proto_programs/generated/dnachisel-num1"
GPCR_COLLECTION = REPO_ROOT / "proto_programs/generated/gpcr-cxcr4-miniprotein"


def _compile_fixture(fixture_id: str):
    spec = load_fixture_spec(fixture_id)
    profile = profile_for_fixture(fixture_id)
    recommendations = recommend_topologies(spec)
    plan = compile_proto_plan(
        spec,
        recommendations[0],
        registry=lookup_registry(profile.registry_name),
    )
    return spec, plan, profile


def test_generate_custom_egfp_matches_committed_sources() -> None:
    spec, plan, profile = _compile_fixture("custom-egfp-lung")
    generated = generate_program_sources(spec, plan, profile=profile)

    for filename, source in generated.items():
        committed = (CUSTOM_COLLECTION / filename).read_text()
        assert source == committed


def test_generate_dnachisel_matches_committed_sources() -> None:
    spec, plan, profile = _compile_fixture("dnachisel-num1")
    generated = generate_program_sources(spec, plan, profile=profile)

    for filename, source in generated.items():
        committed = (DNACHISEL_COLLECTION / filename).read_text()
        assert source == committed


def test_generate_gpcr_cxcr4_matches_committed_sources() -> None:
    spec, plan, profile = _compile_fixture("gpcr-cxcr4-miniprotein")
    generated = generate_program_sources(spec, plan, profile=profile)

    for filename, source in generated.items():
        committed = (GPCR_COLLECTION / filename).read_text()
        assert source == committed


def test_generate_refuses_unresolved_bindings(example_spec: MethodologySpec) -> None:
    recommendations = recommend_topologies(example_spec)
    plan = compile_proto_plan(example_spec, recommendations[0], registry={})

    with pytest.raises(UnresolvedBindingsError, match="unresolved component bindings"):
        generate_program_sources(example_spec, plan)


def test_validate_program_source_rejects_forbidden_import() -> None:
    source = (
        "import os\n\n"
        "def build_program():\n"
        "    return None\n"
    )

    with pytest.raises(ValueError, match="from-imports only"):
        validate_program_source(source, filename="design_bad.py")


def test_validate_program_source_rejects_module_level_side_effects() -> None:
    source = (
        '"""Program."""\n\n'
        "print('side effect')\n\n"
        "def build_program():\n"
        "    return None\n"
    )

    with pytest.raises(ValueError, match="import time"):
        validate_program_source(source, filename="design_bad.py")


def test_generated_modules_are_inert_on_import(tmp_path: Path) -> None:
    spec, plan, profile = _compile_fixture("custom-egfp-lung")
    generated = generate_program_sources(spec, plan, profile=profile)

    for filename, source in generated.items():
        path = tmp_path / filename
        path.write_text(source)
        validate_program_source(source, filename=filename)

        import importlib.util

        module_spec = importlib.util.spec_from_file_location(filename[:-3], path)
        assert module_spec and module_spec.loader
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        assert callable(module.build_program)


def test_require_resolved_plan_accepts_bound_fixture_plan() -> None:
    _, plan, _ = _compile_fixture("custom-egfp-lung")
    assert require_resolved_plan(plan) is plan
