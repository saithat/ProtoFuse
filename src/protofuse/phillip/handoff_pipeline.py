"""Generate and finalize frozen program collections for Sai handoff."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any

from protofuse.phillip import compile_proto_plan, generate_program_sources, recommend_topologies
from protofuse.phillip.generator import finalize_collection
from protofuse.phillip.handoff_config import handoff_config_for
from protofuse.phillip.program_builders import load_fixture_spec
from protofuse.phillip.registries import REGISTRY_VERSION, lookup_registry, profile_for_fixture

REPO_ROOT = Path(__file__).resolve().parents[3]


def git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True)
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def run_handoff_pipeline(
    fixture_id: str,
    *,
    collection_id: str | None = None,
    reviewed: bool = True,
    extra_stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate design_*.py, finalize collection.json, and return timing metadata."""

    config = handoff_config_for(fixture_id)
    collection_id = collection_id or fixture_id
    started = perf_counter()
    stages: list[dict[str, float | str]] = list(extra_stages or [])

    def mark(stage: str) -> None:
        stages.append({"stage": stage, "elapsed_s": round(perf_counter() - started, 3)})

    spec = load_fixture_spec(fixture_id)
    if config.requires_paper_source:
        paper_path = REPO_ROOT / str(spec.paper.source_path)
        if not paper_path.is_file():
            raise FileNotFoundError(f"paper source missing: {paper_path}")
    mark("methodology_fixture")

    recommendations = recommend_topologies(spec)
    profile = profile_for_fixture(fixture_id)
    plan = compile_proto_plan(
        spec,
        recommendations[0],
        registry=lookup_registry(profile.registry_name),
        device=config.compile_device,
    )
    if not plan.executable:
        raise RuntimeError(f"plan not executable: {plan.unresolved}")
    mark("compile_proto_plan")

    sources = generate_program_sources(spec, plan, profile=profile)
    collection_dir = REPO_ROOT / "proto_programs/generated" / collection_id
    collection_dir.mkdir(parents=True, exist_ok=True)
    for filename, program_source in sources.items():
        (collection_dir / filename).write_text(program_source)
    mark("generate_program_sources")

    finalize_collection(
        collection_dir,
        collection_id=collection_id,
        methodology_id=config.methodology_id,
        proto_version=git_head(),
        registry_version=REGISTRY_VERSION,
        seed_policy=config.seed_policy,
        reviewed=reviewed,
    )
    mark("finalize_collection")

    timing: dict[str, Any] = {
        "fixture_id": fixture_id,
        "collection_id": collection_id,
        "methodology_id": config.methodology_id,
        "paper_identifier": spec.paper.identifier,
        "paper_source_path": spec.paper.source_path,
        "topology": recommendations[0].topology.value,
        "compile_device": config.compile_device,
        "total_elapsed_s": round(perf_counter() - started, 3),
        "stages": stages,
        "handoff_path": str(collection_dir.relative_to(REPO_ROOT)),
    }
    timing_path = REPO_ROOT / "workspaces/phillip" / f"TIMING_{collection_id}.json"
    timing_path.write_text(json.dumps(timing, indent=2) + "\n")
    timing["timing_path"] = str(timing_path.relative_to(REPO_ROOT))
    return timing
