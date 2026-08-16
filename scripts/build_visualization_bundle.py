#!/usr/bin/env python3
"""Build a curated, Git-trackable bundle of final design artifacts.

The source analysis/checkpoint directories remain ignored because they may contain raw
teacher traces, credentials, or large provider payloads. This script copies only the
small, reviewed fields needed to render final candidates: sequences, structures,
molecules, scores, labels, and provenance hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode())


def _source_record(path: Path, root: Path) -> dict[str, str]:
    try:
        display = str(path.relative_to(root))
    except ValueError:
        display = path.name
    return {"path": display, "sha256": _sha256_bytes(path.read_bytes())}


def _safe_id(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _sequence_type(sequence: str, supplied: Any = None) -> str:
    if isinstance(supplied, str) and supplied:
        return supplied.lower()
    alphabet = set(sequence.upper())
    return "dna" if alphabet <= set("ACGTUN-") else "protein"


def _write_fasta(path: Path, candidate_id: str, sequence: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wrapped = "\n".join(sequence[index : index + 80] for index in range(0, len(sequence), 80))
    path.write_text(f">{candidate_id}\n{wrapped}\n")


def _candidate(
    *,
    candidate_id: str,
    fixture: str,
    tier: str,
    sequence: str,
    sequence_type: str,
    source: dict[str, str],
    output_dir: Path,
    artifact_role: str = "final",
    complete: bool = True,
    score_vector: list[dict[str, Any]] | None = None,
    segment_label: str = "construct",
) -> dict[str, Any]:
    filename = f"{_safe_id(candidate_id)}.fasta"
    fasta_path = output_dir / "sequences" / filename
    _write_fasta(fasta_path, candidate_id, sequence)
    return {
        "candidate_id": candidate_id,
        "fixture": fixture,
        "tier": tier,
        "arm": "full_model",
        "artifact_role": artifact_role,
        "complete": complete,
        "segment_label": segment_label,
        "sequence": {
            "type": sequence_type,
            "length": len(sequence),
            "value": sequence,
            "sha256": _sha256_text(sequence),
            "fasta_path": f"sequences/{filename}",
        },
        "score_vector": score_vector or [],
        "structure_ids": [],
        "molecule_ids": [],
        "source": source,
    }


def _score_vector(report: dict[str, Any]) -> list[dict[str, Any]]:
    energy = report.get("final_energy")
    if not isinstance(energy, (int, float)):
        return []
    return [
        {
            "name": "final_energy",
            "value": float(energy),
            "direction": "minimize",
            "units": "internal composite",
        }
    ]


def _add_report_candidate(
    candidates: dict[str, dict[str, Any]],
    *,
    report: dict[str, Any],
    source_path: Path,
    root: Path,
    output_dir: Path,
) -> None:
    sequence = report.get("final_sequence")
    fixture = report.get("fixture")
    tier = report.get("tier", "unknown")
    if not isinstance(sequence, str) or not sequence or not isinstance(fixture, str):
        return
    candidate_id = f"{fixture}:{tier}:final"
    candidates[candidate_id] = _candidate(
        candidate_id=candidate_id,
        fixture=fixture,
        tier=str(tier),
        sequence=sequence,
        sequence_type=_sequence_type(sequence),
        source=_source_record(source_path, root),
        output_dir=output_dir,
        score_vector=_score_vector(report),
    )


def _collect_analysis_candidates(
    root: Path,
    analysis_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    candidates: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, str]] = []
    modal_path = analysis_dir / "modal_smoke_summary.json"
    modal = _read_json(modal_path)
    if modal is not None:
        source = _source_record(modal_path, root)
        sources.append(source)
        runs = modal.get("runs", [])
        if isinstance(runs, list):
            for run in runs:
                if isinstance(run, dict):
                    _add_report_candidate(
                        candidates,
                        report=run,
                        source_path=modal_path,
                        root=root,
                        output_dir=output_dir,
                    )
                    prefix = run.get("output_sequence_prefix")
                    fixture = run.get("fixture")
                    tier = run.get("tier", "unknown")
                    if isinstance(prefix, str) and prefix and isinstance(fixture, str):
                        candidate_id = f"{fixture}:{tier}:output-prefix"
                        candidates[candidate_id] = _candidate(
                            candidate_id=candidate_id,
                            fixture=fixture,
                            tier=str(tier),
                            sequence=prefix,
                            sequence_type=_sequence_type(prefix),
                            source=source,
                            output_dir=output_dir,
                            artifact_role="partial_output_prefix",
                            complete=False,
                        )

    for path in sorted(analysis_dir.glob("*/smoke_run_report.json")):
        report = _read_json(path)
        if report is None:
            continue
        sources.append(_source_record(path, root))
        _add_report_candidate(
            candidates,
            report=report,
            source_path=path,
            root=root,
            output_dir=output_dir,
        )
    return candidates, sources


def _structure_text(payload: Any) -> tuple[str, str] | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("structure")
    if not isinstance(value, str) or not value:
        return None
    supplied_format = payload.get("structure_format")
    if supplied_format in {"pdb", "cif"}:
        return value, str(supplied_format)
    return value, "pdb" if value.startswith(("ATOM", "HEADER", "MODEL")) else "cif"


def _normalized_structure_text(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()) + "\n"


def _collect_checkpoint_candidates(
    root: Path,
    checkpoint_dir: Path,
    output_dir: Path,
    candidates: dict[str, dict[str, Any]],
    structures: list[dict[str, Any]],
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for path in sorted(checkpoint_dir.glob("*/*/program-*.json")):
        record = _read_json(path)
        if record is None:
            continue
        source = _source_record(path, root)
        sources.append(source)
        stages = record.get("stages", {})
        if not isinstance(stages, dict) or not stages:
            continue
        stage_items = [
            (int(key), value)
            for key, value in stages.items()
            if str(key).isdigit() and isinstance(value, dict)
        ]
        if not stage_items:
            continue
        stage_index, stage = max(stage_items, key=lambda item: item[0])
        state = stage.get("state", {})
        segments = state.get("segments", []) if isinstance(state, dict) else []
        if not isinstance(segments, list):
            continue
        run_id = str(record.get("run_id", path.parents[1].name))
        tier = str(record.get("tier", path.parent.name))
        program_index = int(record.get("program_index", 0))
        energies = state.get("energy_scores", []) if isinstance(state, dict) else []
        for segment_index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            label = str(segment.get("label", f"segment-{segment_index}"))
            results = segment.get("result", [])
            if not isinstance(results, list):
                continue
            for result_index, result in enumerate(results):
                if not isinstance(result, dict):
                    continue
                sequence = result.get("sequence")
                if not isinstance(sequence, str) or not sequence:
                    continue
                candidate_id = (
                    f"{run_id}:{tier}:program-{program_index}:stage-{stage_index}:"
                    f"{label}:result-{result_index}"
                )
                score_vector: list[dict[str, Any]] = []
                if isinstance(energies, list) and result_index < len(energies):
                    energy = energies[result_index]
                    if isinstance(energy, (int, float)):
                        score_vector = [
                            {
                                "name": "final_energy",
                                "value": float(energy),
                                "direction": "minimize",
                                "units": "internal composite",
                            }
                        ]
                candidate = _candidate(
                    candidate_id=candidate_id,
                    fixture=run_id,
                    tier=tier,
                    sequence=sequence,
                    sequence_type=_sequence_type(sequence, result.get("sequence_type")),
                    source=source,
                    output_dir=output_dir,
                    score_vector=score_vector,
                    segment_label=label,
                )
                structure_payload = _structure_text(result.get("structure"))
                if structure_payload is not None:
                    structure_value, structure_format = structure_payload
                    structure_id = f"{candidate_id}:structure"
                    structure_filename = f"{_safe_id(structure_id)}.{structure_format}"
                    structure_path = output_dir / "structures" / structure_filename
                    structure_path.parent.mkdir(parents=True, exist_ok=True)
                    structure_path.write_text(_normalized_structure_text(structure_value))
                    structures.append(
                        _structure_record(
                            structure_id=structure_id,
                            candidate_id=candidate_id,
                            role="final_attached_structure",
                            path=structure_path,
                            output_dir=output_dir,
                            source=source,
                        )
                    )
                    candidate["structure_ids"].append(structure_id)
                candidates[candidate_id] = candidate
    return sources


def _pdb_summary(path: Path) -> dict[str, Any]:
    atom_count = 0
    hetatm_count = 0
    chains: set[str] = set()
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("ATOM  "):
            atom_count += 1
            if len(line) > 21 and line[21].strip():
                chains.add(line[21])
        elif line.startswith("HETATM"):
            hetatm_count += 1
            if len(line) > 21 and line[21].strip():
                chains.add(line[21])
    return {
        "atom_count": atom_count,
        "hetatm_count": hetatm_count,
        "chain_ids": sorted(chains),
    }


def _structure_record(
    *,
    structure_id: str,
    candidate_id: str,
    role: str,
    path: Path,
    output_dir: Path,
    source: dict[str, str],
) -> dict[str, Any]:
    structure_format = path.suffix.lower().lstrip(".")
    summary = _pdb_summary(path) if structure_format == "pdb" else {}
    return {
        "structure_id": structure_id,
        "candidate_id": candidate_id,
        "role": role,
        "format": structure_format,
        "path": str(path.relative_to(output_dir)),
        "sha256": _sha256_bytes(path.read_bytes()),
        **summary,
        "source": source,
    }


def _collect_known_structures(
    root: Path,
    analysis_dir: Path,
    output_dir: Path,
    candidates: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    structures: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    source_path = analysis_dir / "rfdiffusion3-boltz2-binder" / "last_rfdiffusion_structure.pdb"
    candidate_id = "rfdiffusion3-boltz2-binder:smoke:final"
    if source_path.is_file():
        source = _source_record(source_path, root)
        sources.append(source)
        destination = output_dir / "structures" / "rfdiffusion3-boltz2-binder-intermediate.pdb"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(_normalized_structure_text(source_path.read_text()))
        structure_id = "rfdiffusion3-boltz2-binder:smoke:intermediate-backbone"
        structures.append(
            _structure_record(
                structure_id=structure_id,
                candidate_id=candidate_id,
                role="intermediate_rfdiffusion_backbone",
                path=destination,
                output_dir=output_dir,
                source=source,
            )
        )
        if candidate_id in candidates:
            candidates[candidate_id]["structure_ids"].append(structure_id)
    return structures, sources


def build_bundle(
    root: Path,
    *,
    analysis_dir: Path,
    checkpoint_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, sources = _collect_analysis_candidates(root, analysis_dir, output_dir)
    structures, structure_sources = _collect_known_structures(
        root, analysis_dir, output_dir, candidates
    )
    sources.extend(structure_sources)
    sources.extend(
        _collect_checkpoint_candidates(
            root,
            checkpoint_dir,
            output_dir,
            candidates,
            structures,
        )
    )
    unique_sources = {source["path"]: source for source in sources}
    final_candidates = sorted(candidates.values(), key=lambda item: item["candidate_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "bundle_id": "protofuse-visualization-v1",
        "description": (
            "Curated final-candidate artifacts for sequence, structure, molecule, and "
            "full-versus-fused visualizations."
        ),
        "candidates": final_candidates,
        "structures": sorted(structures, key=lambda item: item["structure_id"]),
        "molecules": [],
        "gaps": [
            {
                "code": "VIS-MOLECULE-001",
                "message": "No final small-molecule SMILES or SDF artifacts are available.",
            },
            {
                "code": "VIS-STRUCTURE-001",
                "message": (
                    "The committed RFdiffusion PDB is an intermediate backbone; final "
                    "Boltz/ESMFold structures are not yet exported."
                ),
            },
            {
                "code": "VIS-SURROGATE-001",
                "message": (
                    "The CUSTOM surrogate report stores agreement counts but not paired final "
                    "sequences, so a full-versus-fused sequence alignment cannot be rendered."
                ),
            },
        ],
        "provenance": sorted(unique_sources.values(), key=lambda item: item["path"]),
    }


def _resolve(root: Path, supplied: Path | None, default: str) -> Path:
    if supplied is None:
        return root / default
    return supplied if supplied.is_absolute() else root / supplied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--analysis-dir", type=Path, default=None)
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    analysis_dir = _resolve(root, args.analysis_dir, "data/analysis")
    checkpoint_dir = _resolve(root, args.checkpoint_dir, "data/runs/checkpoints")
    output_dir = _resolve(root, args.output_dir, "data/visualizations")
    bundle = build_bundle(
        root,
        analysis_dir=analysis_dir,
        checkpoint_dir=checkpoint_dir,
        output_dir=output_dir,
    )
    if args.strict and not bundle["candidates"]:
        raise SystemExit("no final or partial candidate sequences were found")
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    print(
        f"wrote {manifest_path} with {len(bundle['candidates'])} candidates, "
        f"{len(bundle['structures'])} structures, and {len(bundle['molecules'])} molecules"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
