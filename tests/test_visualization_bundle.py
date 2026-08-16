from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_visualization_bundle.py"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_bundle_exports_reviewed_final_artifacts_without_raw_proposals(
    tmp_path: Path,
) -> None:
    analysis = tmp_path / "data" / "analysis"
    _write_json(
        analysis / "modal_smoke_summary.json",
        {
            "runs": [
                {
                    "fixture": "protein-demo",
                    "tier": "smoke",
                    "final_sequence": "MPEPTIDE",
                },
                {
                    "fixture": "partial-demo",
                    "tier": "smoke",
                    "output_sequence_prefix": "ACDE",
                },
            ]
        },
    )
    _write_json(
        analysis / "dna-demo" / "smoke_run_report.json",
        {
            "fixture": "dna-demo",
            "tier": "smoke",
            "final_sequence": "ATGCATGC",
            "final_energy": 1.5,
        },
    )
    checkpoint = tmp_path / "data" / "runs" / "checkpoints" / "checkpoint-demo" / "full"
    _write_json(
        checkpoint / "program-0000.json",
        {
            "run_id": "checkpoint-demo",
            "tier": "full",
            "program_index": 0,
            "stages": {
                "0": {
                    "state": {
                        "energy_scores": [0.25],
                        "segments": [
                            {
                                "label": "binder",
                                "result": [
                                    {
                                        "sequence": "ACDEFG",
                                        "sequence_type": "protein",
                                        "structure": {
                                            "structure": (
                                                "ATOM      1  CA  ALA A   1      "
                                                "0.000   0.000   0.000  1.00 20.00           C\n"
                                            ),
                                            "structure_format": "pdb",
                                        },
                                    }
                                ],
                                "proposals": [{"sequence": "SECRET_RAW_PROPOSAL"}],
                            }
                        ],
                    }
                }
            },
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--strict",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    output = tmp_path / "data" / "visualizations"
    manifest_text = (output / "manifest.json").read_text()
    manifest = json.loads(manifest_text)
    by_id = {item["candidate_id"]: item for item in manifest["candidates"]}

    assert "protein-demo:smoke:final" in by_id
    assert by_id["protein-demo:smoke:final"]["sequence"]["length"] == 8
    assert by_id["dna-demo:smoke:final"]["sequence"]["type"] == "dna"
    assert by_id["partial-demo:smoke:output-prefix"]["complete"] is False
    checkpoint_id = "checkpoint-demo:full:program-0:stage-0:binder:result-0"
    assert by_id[checkpoint_id]["score_vector"][0]["value"] == 0.25
    assert by_id[checkpoint_id]["structure_ids"]
    assert "SECRET_RAW_PROPOSAL" not in manifest_text

    structure = manifest["structures"][0]
    assert structure["role"] == "final_attached_structure"
    assert structure["atom_count"] == 1
    assert (output / structure["path"]).is_file()
    for candidate in manifest["candidates"]:
        assert (output / candidate["sequence"]["fasta_path"]).is_file()


def test_committed_manifest_has_required_visualization_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data" / "visualizations" / "manifest.json").read_text())

    assert manifest["schema_version"] == "1.0"
    assert manifest["candidates"]
    assert all(candidate["sequence"]["sha256"] for candidate in manifest["candidates"])
    assert all("artifact_role" in candidate for candidate in manifest["candidates"])
    assert all("source" in candidate for candidate in manifest["candidates"])
    assert isinstance(manifest["structures"], list)
    assert isinstance(manifest["molecules"], list)
    assert any(gap["code"] == "VIS-MOLECULE-001" for gap in manifest["gaps"])
