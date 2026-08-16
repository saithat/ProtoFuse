"""Automated review gate for a fixture and its frozen program collection.

Covers every mechanical handoff check so a human review is only the
paper-fidelity judgement that cannot be machine-verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from protofuse.phillip.compiler import compile_proto_plan
from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.generator import (
    ProgramSourceValidationError,
    generate_program_sources,
    validate_program_source,
)
from protofuse.phillip.handoff_config import handoff_config_for
from protofuse.phillip.program_builders import load_fixture_spec
from protofuse.phillip.registries import REGISTRY_VERSION, lookup_registry, profile_for_fixture
from protofuse.phillip.topology import recommend_topologies
from protofuse.program_collection import load_collection

REPO_ROOT = Path(__file__).resolve().parents[3]
COLLECTIONS_DIR = REPO_ROOT / "proto_programs" / "generated"

CheckStatus = Literal["pass", "warn", "fail", "skip"]

_STATUS_LABEL: dict[CheckStatus, str] = {
    "pass": "PASS",
    "warn": "WARN",
    "fail": "FAIL",
    "skip": "SKIP",
}


@dataclass(frozen=True)
class ReviewCheck:
    name: str
    status: CheckStatus
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class ReviewReport:
    fixture_id: str
    collection_id: str
    checks: list[ReviewCheck] = field(default_factory=list)

    def add(self, name: str, status: CheckStatus, detail: str) -> None:
        self.checks.append(ReviewCheck(name=name, status=status, detail=detail))

    @property
    def failed(self) -> list[ReviewCheck]:
        return [check for check in self.checks if check.status == "fail"]

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        width = max(len(check.name) for check in self.checks)
        lines = [f"review {self.fixture_id} -> collection {self.collection_id}"]
        for check in self.checks:
            label = _STATUS_LABEL[check.status]
            lines.append(f"  {label:<4} {check.name:<{width}}  {check.detail}")
        verdict = "READY FOR HANDOFF" if self.ok else "BLOCKED"
        lines.append(f"  => {verdict}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "collection_id": self.collection_id,
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
        }


def _components(spec: MethodologySpec) -> list[tuple[str, str, int]]:
    groups = (
        ("generator", spec.generators),
        ("constraint", spec.constraints),
        ("optimizer", spec.optimizers),
    )
    return [(kind, item.name, len(item.evidence)) for kind, items in groups for item in items]


def _check_evidence(report: ReviewReport, spec: MethodologySpec) -> None:
    components = _components(spec)
    missing = [f"{kind} {name!r}" for kind, name, count in components if count == 0]
    if missing:
        report.add(
            "evidence_coverage",
            "fail",
            f"{len(missing)}/{len(components)} components have no paper evidence: "
            + ", ".join(missing),
        )
        return
    quotes = sum(count for _, _, count in components)
    report.add(
        "evidence_coverage",
        "pass",
        f"{len(components)} components carry {quotes} evidence quotes",
    )


def _check_disclosure(report: ReviewReport, spec: MethodologySpec) -> None:
    if not spec.assumptions and not spec.unknowns:
        report.add(
            "disclosure",
            "warn",
            "no assumptions or unknowns recorded; confirm nothing was simplified silently",
        )
        return
    report.add(
        "disclosure",
        "pass",
        f"{len(spec.assumptions)} assumptions, {len(spec.unknowns)} unknowns disclosed",
    )


def _check_paper_source(report: ReviewReport, spec: MethodologySpec, *, required: bool) -> None:
    source_path = spec.paper.source_path
    if not source_path:
        status: CheckStatus = "fail" if required else "warn"
        report.add("paper_source", status, "methodology declares no paper.source_path")
        return
    resolved = REPO_ROOT / source_path
    if resolved.is_file():
        report.add("paper_source", "pass", f"{source_path} present locally")
        return
    status = "fail" if required else "warn"
    report.add(
        "paper_source",
        status,
        f"{source_path} missing locally (papers are gitignored; required={required})",
    )


def _check_paper_identity(report: ReviewReport, spec: MethodologySpec) -> None:
    if not spec.paper.identifier:
        report.add("paper_identity", "warn", "no DOI/PMID/arXiv identifier recorded")
        return
    report.add(
        "paper_identity",
        "warn",
        f"identifier {spec.paper.identifier!r} not machine-verified; needs human or web check",
    )


def _check_sources(
    report: ReviewReport,
    spec: MethodologySpec,
    plan: Any,
    profile: Any,
    collection_dir: Path,
) -> None:
    try:
        expected = generate_program_sources(spec, plan, profile=profile)
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        report.add("source_drift", "fail", f"regeneration failed: {exc}")
        return

    committed = {path.name: path for path in sorted(collection_dir.glob("design_*.py"))}
    missing = sorted(set(expected) - set(committed))
    extra = sorted(set(committed) - set(expected))
    drifted = [
        name
        for name in sorted(set(expected) & set(committed))
        if committed[name].read_text() != expected[name]
    ]
    problems = []
    if missing:
        problems.append(f"missing {missing}")
    if extra:
        problems.append(f"unexpected {extra}")
    if drifted:
        problems.append(f"hand-edited {drifted}")
    if problems:
        report.add("source_drift", "fail", "; ".join(problems))
    else:
        report.add(
            "source_drift",
            "pass",
            f"{len(expected)} programs byte-identical to generator output",
        )

    violations: list[str] = []
    for name, path in committed.items():
        try:
            validate_program_source(path.read_text(), filename=name)
        except ProgramSourceValidationError as exc:
            violations.append(str(exc))
    if violations:
        report.add("source_safety", "fail", "; ".join(violations))
    else:
        report.add(
            "source_safety",
            "pass",
            f"{len(committed)} programs use allow-listed imports and are inert on import",
        )


def _check_manifest(report: ReviewReport, collection_dir: Path, methodology_id: str) -> None:
    try:
        loaded = load_collection(collection_dir, require_reviewed=True)
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        report.add("manifest", "fail", f"{exc}")
        return

    manifest = loaded.manifest
    report.add(
        "manifest",
        "pass",
        f"reviewed=True, {len(manifest.programs)} programs, hashes match",
    )

    if manifest.methodology_id != methodology_id:
        report.add(
            "manifest_metadata",
            "fail",
            f"methodology_id {manifest.methodology_id!r} != handoff config {methodology_id!r}",
        )
        return
    if manifest.registry_version != REGISTRY_VERSION:
        report.add(
            "manifest_metadata",
            "fail",
            f"registry_version {manifest.registry_version!r} != current {REGISTRY_VERSION!r}",
        )
        return
    report.add(
        "manifest_metadata",
        "pass",
        f"methodology={manifest.methodology_id}, registry={manifest.registry_version}",
    )


def _check_structure_binding(report: ReviewReport, spec: MethodologySpec) -> None:
    """Resolve PDB coordinates and hotspot labels before GPU tools bind them."""

    from protofuse.phillip.program_builders import (
        _hotspot_residue_string,
        _target_structure_from_pdb,
    )

    params = spec.global_parameters
    pdb_id = params.get("target_pdb")
    if not pdb_id:
        report.add("structure_binding", "skip", "no target_pdb in global_parameters")
        return

    try:
        structure = _target_structure_from_pdb(str(pdb_id))
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        report.add("structure_binding", "fail", f"{pdb_id}: {exc}")
        return

    hotspots = params.get("target_hotspots") or params.get("hotspots") or []
    hotspot_residues = _hotspot_residue_string([str(item) for item in hotspots])
    chains = params.get("target_chains") or ["A"]
    detail = (
        f"{pdb_id} resolved via RCSB ({len(structure.structure)} chars), "
        f"chains={list(chains)}"
    )
    if hotspots:
        detail += f", hotspots={list(hotspots)} -> {hotspot_residues!r}"
    off_target = params.get("off_target_pdb")
    if off_target:
        try:
            off_structure = _target_structure_from_pdb(str(off_target))
        except Exception as exc:  # noqa: BLE001 - reported as a failed check
            report.add("structure_binding", "fail", f"off_target {off_target}: {exc}")
            return
        detail += f"; off_target {off_target} ok ({len(off_structure.structure)} chars)"
    report.add("structure_binding", "pass", detail)


def _check_preflight(report: ReviewReport, fixture_id: str, target_length: int | None) -> None:
    import logging

    from protofuse.phillip.workload_preflight import run_preflight

    logging.disable(logging.CRITICAL)
    try:
        preflight = run_preflight(fixture_id, target_length=target_length)
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        report.add("preflight", "fail", f"{exc}")
        return

    detail = f"classification={preflight.classification} at length={preflight.target_length}"
    report.add("preflight", "pass" if preflight.classification == "ok" else "fail", detail)


def review_fixture(
    fixture_id: str,
    *,
    collection_id: str | None = None,
    run_preflight_check: bool = True,
    preflight_length: int | None = None,
) -> ReviewReport:
    """Run every machine-checkable handoff gate for one fixture."""

    collection_id = collection_id or fixture_id
    report = ReviewReport(fixture_id=fixture_id, collection_id=collection_id)
    config = handoff_config_for(fixture_id)

    try:
        spec = load_fixture_spec(fixture_id)
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        report.add("fixture_spec", "fail", f"{exc}")
        return report
    report.add("fixture_spec", "pass", f"schema v{spec.schema_version}: {spec.paper.title}")

    _check_paper_identity(report, spec)
    _check_paper_source(report, spec, required=config.requires_paper_source)
    _check_evidence(report, spec)
    _check_disclosure(report, spec)

    try:
        profile = profile_for_fixture(fixture_id)
    except ValueError as exc:
        report.add("workload_profile", "fail", f"{exc}")
        return report
    report.add(
        "workload_profile",
        "pass",
        f"workload={profile.workload_key}, registry={profile.registry_name}",
    )

    try:
        plan = compile_proto_plan(
            spec,
            recommend_topologies(spec)[0],
            registry=lookup_registry(profile.registry_name),
            device=config.compile_device,
        )
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        report.add("plan_bindings", "fail", f"{exc}")
        return report
    if not plan.executable:
        report.add("plan_bindings", "fail", f"unresolved bindings: {plan.unresolved}")
        return report
    report.add(
        "plan_bindings",
        "pass",
        f"{len(plan.bindings)} bindings resolved, topology={plan.topology.value}",
    )

    collection_dir = COLLECTIONS_DIR / collection_id
    if not collection_dir.is_dir():
        report.add("collection", "fail", f"missing {collection_dir.relative_to(REPO_ROOT)}/")
        return report

    _check_sources(report, spec, plan, profile, collection_dir)
    _check_manifest(report, collection_dir, config.methodology_id)
    _check_structure_binding(report, spec)

    if run_preflight_check:
        _check_preflight(report, fixture_id, preflight_length)
    else:
        report.add("preflight", "skip", "skipped by request")

    return report
