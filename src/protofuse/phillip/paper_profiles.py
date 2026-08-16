"""Paper metadata and replication summaries for frozen program collections."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.paper_review import DOI_RE, PaperRecord, fetch_paper_record
from protofuse.phillip.program_builders import load_fixture_spec

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "workspaces" / "phillip" / "fixtures"
FIGURES_DIR = REPO_ROOT / "data" / "papers" / "figures"
MANIFEST_PATH = REPO_ROOT / "data" / "papers" / "figure_manifest.json"

INTERNAL_REFERENCE_NOTES: dict[str, str] = {
    "esm2-protein-maturation": (
        "Internal ProtoFuse developability benchmark (no single canonical paper). "
        "Topology follows iterative refinement with ESM-2 + ESMFold MCMC."
    ),
    "antibody-cdr-maturation": (
        "Internal antibody CDR maturation benchmark inspired by region-local antibody "
        "design workflows; parameters live in CANDIDATE_WORKFLOWS.md."
    ),
    "freebindcraft-binder": (
        "PyRosetta-free BindCraft alternative (FreeBindCraft, 2025). "
        "No registered DOI in the fixture."
    ),
    "symmetric-oligomer-ring": (
        "Symmetric nanoring design benchmark from CANDIDATE_WORKFLOWS.md."
    ),
    "ppi-interface-specificity": (
        "Dual target/off-target interface specificity benchmark from CANDIDATE_WORKFLOWS.md."
    ),
    "rfdiffusion3-boltz2-binder": (
        "RFdiffusion3 + Boltz-2 cycling benchmark from CANDIDATE_WORKFLOWS.md."
    ),
    "ligandmpnn-enzyme-redesign": (
        "Ligand-aware enzyme active-site redesign benchmark from CANDIDATE_WORKFLOWS.md."
    ),
    "bioemu-ensemble-filter": (
        "BioEmu conformational ensemble filtering benchmark (2024–2025 literature)."
    ),
}

# Curated primary figure per collection (Fig 1 unless the replicated result is clearer elsewhere).
PRIMARY_FIGURE_IDS: dict[str, str] = {
    "custom-egfp-lung": "Fig3",
    "dnachisel-num1": "Fig1",
    "gpcr-cxcr4-miniprotein": "Fig1",
    "boltz2-state-sweep": "F1",
}


@dataclass(frozen=True)
class FigureCandidate:
    figure_id: str
    label: str
    caption: str
    file: str | None
    url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.figure_id,
            "label": self.label,
            "caption": self.caption,
            "file": self.file,
            "url": self.url,
        }


@dataclass
class PaperProfile:
    collection_id: str
    fixture_title: str
    identifier: str | None
    is_doi: bool
    registered: PaperRecord | None = None
    abstract: str | None = None
    reference_note: str | None = None
    replicated: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    not_replicated: list[str] = field(default_factory=list)
    figure_candidates: list[FigureCandidate] = field(default_factory=list)
    approved_figure_id: str | None = None

    @property
    def display_title(self) -> str:
        if self.registered and self.registered.title:
            return self.registered.title
        return self.fixture_title

    @property
    def display_doi(self) -> str | None:
        if self.identifier and self.is_doi:
            return self.identifier
        return None

    @property
    def doi_link(self) -> str | None:
        doi = self.display_doi
        return f"https://doi.org/{doi}" if doi else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "fixture_title": self.fixture_title,
            "identifier": self.identifier,
            "is_doi": self.is_doi,
            "display_title": self.display_title,
            "display_doi": self.display_doi,
            "abstract": self.abstract,
            "reference_note": self.reference_note,
            "replicated": self.replicated,
            "assumptions": self.assumptions,
            "not_replicated": self.not_replicated,
            "figure_candidates": [candidate.as_dict() for candidate in self.figure_candidates],
            "approved_figure_id": self.approved_figure_id,
        }


def _summarize_replicated(spec: MethodologySpec) -> list[str]:
    lines: list[str] = []
    for generator in spec.generators:
        if generator.evidence:
            lines.append(f"**Generator — {generator.name}:** {generator.description}")
    for constraint in spec.constraints:
        if constraint.evidence:
            lines.append(f"**Constraint — {constraint.name}:** {constraint.description}")
    for optimizer in spec.optimizers:
        if optimizer.evidence:
            lines.append(f"**Optimizer — {optimizer.name}:** {optimizer.description}")
    for step in spec.workflow.steps:
        if step.evidence:
            lines.append(f"**Workflow step — {step.id}:** {step.operation}")
    return lines


def load_figure_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {}
    payload = json.loads(MANIFEST_PATH.read_text())
    return payload if isinstance(payload, dict) else {}


def save_figure_manifest(payload: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _figure_candidates_from_manifest(
    collection_id: str,
    manifest: dict[str, Any],
) -> tuple[list[FigureCandidate], str | None]:
    entry = manifest.get(collection_id, {})
    if not isinstance(entry, dict):
        return [], None
    candidates: list[FigureCandidate] = []
    raw_candidates = entry.get("candidates", [])
    if not raw_candidates and isinstance(entry.get("primary"), dict):
        raw_candidates = [entry["primary"]]
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        candidates.append(
            FigureCandidate(
                figure_id=str(raw.get("id", "")),
                label=str(raw.get("label", raw.get("id", "Figure"))),
                caption=str(raw.get("caption", "")),
                file=str(raw["file"]) if raw.get("file") else None,
                url=str(raw["url"]) if raw.get("url") else None,
            )
        )
    approved = entry.get("approved")
    return candidates, str(approved) if approved else None


def load_paper_profile(
    collection_id: str,
    *,
    manifest: dict[str, Any] | None = None,
    fetch_online: bool = False,
) -> PaperProfile:
    spec = load_fixture_spec(collection_id)
    identifier = spec.paper.identifier
    is_doi = bool(identifier and DOI_RE.match(identifier))

    registered: PaperRecord | None = None
    abstract: str | None = None
    if is_doi:
        assert identifier is not None
        registered = fetch_paper_record(
            identifier,
            use_cache=True,
            refresh=fetch_online,
        )
        if registered:
            abstract = registered.abstract

    if abstract is None and spec.paper.title:
        abstract = None

    manifest = manifest if manifest is not None else load_figure_manifest()
    figure_candidates, approved_figure_id = _figure_candidates_from_manifest(
        collection_id, manifest
    )

    return PaperProfile(
        collection_id=collection_id,
        fixture_title=spec.paper.title,
        identifier=identifier,
        is_doi=is_doi,
        registered=registered,
        abstract=abstract,
        reference_note=INTERNAL_REFERENCE_NOTES.get(collection_id),
        replicated=_summarize_replicated(spec),
        assumptions=list(spec.assumptions),
        not_replicated=list(spec.unknowns),
        figure_candidates=figure_candidates,
        approved_figure_id=approved_figure_id,
    )


def load_all_paper_profiles(*, fetch_online: bool = False) -> dict[str, PaperProfile]:
    manifest = load_figure_manifest()
    profiles: dict[str, PaperProfile] = {}
    for fixture_dir in sorted(FIXTURES_DIR.iterdir()):
        if not fixture_dir.is_dir():
            continue
        if not (fixture_dir / "methodology.json").is_file():
            continue
        collection_id = fixture_dir.name
        profiles[collection_id] = load_paper_profile(
            collection_id,
            manifest=manifest,
            fetch_online=fetch_online,
        )
    return profiles


def update_approved_figure(collection_id: str, figure_id: str | None) -> None:
    manifest = load_figure_manifest()
    entry = manifest.setdefault(collection_id, {})
    if not isinstance(entry, dict):
        entry = {}
        manifest[collection_id] = entry
    entry["approved"] = figure_id
    save_figure_manifest(manifest)


def resolve_figure_path(candidate: FigureCandidate) -> Path | None:
    if candidate.file:
        path = REPO_ROOT / candidate.file
        if path.is_file():
            return path
    return None


def primary_figure_id(collection_id: str, *, approved: str | None = None) -> str | None:
    if approved:
        return approved
    return PRIMARY_FIGURE_IDS.get(collection_id)


def primary_figure(profile: PaperProfile) -> FigureCandidate | None:
    target_id = primary_figure_id(profile.collection_id, approved=profile.approved_figure_id)
    if target_id:
        for candidate in profile.figure_candidates:
            if candidate.figure_id == target_id:
                return candidate
    return profile.figure_candidates[0] if profile.figure_candidates else None


def figure_image_src(candidate: FigureCandidate) -> str | None:
    local_path = resolve_figure_path(candidate)
    if local_path is not None:
        web_path = _web_display_path(local_path)
        if web_path.is_file():
            return str(web_path)
        if local_path.suffix.lower() in {".tif", ".tiff"}:
            return candidate.url or str(local_path)
        return str(local_path)
    return candidate.url


def _web_display_path(local_path: Path) -> Path:
    """Prefer a pre-optimized sibling JPEG when present."""

    web_jpg = local_path.with_name(f"{local_path.stem}-web.jpg")
    if web_jpg.is_file():
        return web_jpg
    plain_jpg = local_path.with_suffix(".jpg")
    if plain_jpg.is_file() and local_path.suffix.lower() in {".png", ".tif", ".tiff"}:
        return plain_jpg
    return local_path


def apply_primary_figure_approvals() -> None:
    """Write curated primary-figure ids into figure_manifest.json."""

    from protofuse.phillip.paper_figures import sync_all_primary_figures

    sync_all_primary_figures(fetch_if_missing=False)
