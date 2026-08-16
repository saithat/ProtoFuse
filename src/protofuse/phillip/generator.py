"""Generate and finalize Phillip Proto source as validated collections."""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Mapping
from pathlib import Path

from protofuse.phillip.compiler import require_resolved_plan
from protofuse.phillip.contracts import MethodologySpec, ProtoPlan
from protofuse.phillip.registries import ProgramVariant, WorkloadProfile, profile_for_spec
from protofuse.program_collection import ProgramCollection, write_collection_manifest

ALLOWED_IMPORT_ROOTS = frozenset({"__future__", "proto_language", "protofuse"})
ALLOWED_PROGRAM_BUILDER_SYMBOLS = frozenset(
    {
        "build_antibody_cdr_maturation_program",
        "build_af3_boltz2_state_sweep_program",
        "build_bioemu_ensemble_filter_program",
        "build_boltz2_state_sweep_program",
        "build_custom_egfp_program",
        "build_dnachisel_num1_program",
        "build_esm2_protein_maturation_program",
        "build_evo2_regulatory_design_program",
        "build_freebindcraft_binder_program",
        "build_gpcr_cxcr4_miniprotein_program",
        "build_ligandmpnn_enzyme_redesign_program",
        "build_ppi_interface_specificity_program",
        "build_rfdiffusion3_boltz2_binder_program",
        "build_rfdiffusion3_af3_ppi_program",
        "build_symmetric_oligomer_ring_program",
        "load_fixture_spec",
        "resolve_workload_params",
    }
)


class ProgramSourceValidationError(ValueError):
    """Raised when generated or reviewed program source violates handoff rules."""


def _format_docstring(text: str) -> str:
    body = textwrap.dedent(text).strip("\n")
    escaped = body.replace('"""', '\\"""')
    if "\n" not in body:
        return f'"""{escaped}"""'
    return f'"""{escaped}\n"""'


def render_design_program(
    *,
    variant: ProgramVariant,
    fixture_id: str,
    builder_symbol: str,
) -> str:
    """Render one readable `design_*.py` module from a reviewed workload profile."""

    return (
        f"{_format_docstring(variant.docstring)}\n\n"
        "from __future__ import annotations\n\n"
        "from proto_language.core import Program\n\n"
        "from protofuse.phillip.program_builders import (\n"
        f"    {builder_symbol},\n"
        "    load_fixture_spec,\n"
        "    resolve_workload_params,\n"
        ")\n\n\n"
        "def build_program() -> Program:\n"
        f'    spec = load_fixture_spec("{fixture_id}")\n'
        f'    params = resolve_workload_params(spec, tier="{variant.tier}")\n'
        f"    return {variant.builder_call}\n"
    )


def generate_program_sources(
    spec: MethodologySpec,
    plan: ProtoPlan,
    *,
    profile: WorkloadProfile | None = None,
) -> dict[str, str]:
    """Generate design program sources; refuse while bindings are unresolved."""

    require_resolved_plan(plan)
    resolved_profile = profile or profile_for_spec(spec)
    workload = spec.global_parameters.get("workload")
    if resolved_profile.workload_key != workload:
        raise ValueError(
            "profile "
            f"{resolved_profile.workload_key!r} does not match methodology workload {workload!r}"
        )
    sources: dict[str, str] = {}
    for variant in resolved_profile.variants:
        source = render_design_program(
            variant=variant,
            fixture_id=resolved_profile.fixture_id,
            builder_symbol=resolved_profile.builder_symbol,
        )
        validate_program_source(source, filename=variant.filename)
        sources[variant.filename] = source
    return sources


def write_design_programs(
    output_dir: Path,
    sources: Mapping[str, str],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for filename, source in sorted(sources.items()):
        path = output_dir / filename
        path.write_text(source)
        paths.append(path)
    return paths


def validate_program_source(source: str, *, filename: str = "<program>") -> None:
    """Ensure imports are allow-listed and the module is inert on import."""

    tree = ast.parse(source, filename=filename)
    for node in tree.body:
        if isinstance(node, ast.Import):
            raise ProgramSourceValidationError(f"{filename} must use explicit from-imports only")
        if isinstance(node, ast.ImportFrom):
            _validate_import_from(node, filename=filename)

    if not _module_is_inert(tree):
        raise ProgramSourceValidationError(
            f"{filename} must not execute code at import time (only imports and build_program)"
        )

    builders = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "build_program"
    ]
    if len(builders) != 1 or isinstance(builders[0], ast.AsyncFunctionDef):
        raise ProgramSourceValidationError(
            f"{filename} must define exactly one synchronous build_program()"
        )


def _module_is_inert(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, (ast.ImportFrom, ast.FunctionDef)):
            continue
        return False
    return True


def _validate_import_from(node: ast.ImportFrom, *, filename: str) -> None:
    module = node.module or ""
    root = module.split(".", 1)[0]
    if root not in ALLOWED_IMPORT_ROOTS:
        raise ProgramSourceValidationError(f"{filename} import not allow-listed: {module}")

    if module == "protofuse.phillip.program_builders":
        for alias in node.names:
            if alias.name not in ALLOWED_PROGRAM_BUILDER_SYMBOLS:
                raise ProgramSourceValidationError(
                    f"{filename} builder import not allow-listed: {alias.name}"
                )
        return

    if module != "__future__" and module != "proto_language.core":
        raise ProgramSourceValidationError(f"{filename} import not allow-listed: {module}")


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
        validate_program_source(path.read_text(), filename=path.name)
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
