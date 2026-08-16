from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_evaluation_report.py"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_static_report_is_self_contained_and_uses_supplied_results(tmp_path: Path) -> None:
    analysis = tmp_path / "data" / "analysis"
    _write_json(
        analysis / "modal_smoke_summary.json",
        {
            "recorded_at": "2026-08-15",
            "runs": [
                {
                    "fixture": "esm2-protein-maturation",
                    "tier": "smoke",
                    "status": "ok",
                    "num_steps": 5,
                    "wall_seconds": 12.5,
                    "final_sequence": "MUST_NOT_APPEAR_IN_REPORT",
                }
            ],
        },
    )
    _write_json(
        analysis / "custom-egfp-lung" / "surrogate_pilot_report.json",
        {
            "teacher_samples": 10,
            "teacher_collection_seconds": 1.25,
            "splits": {"train": 6, "calibration": 2, "audit": 2},
            "calibration": {"tissue_mae": 0.11, "gc_percentage_point_mae": 0.22},
            "audit": {"tissue_mae": 0.1, "gc_percentage_point_mae": 0.2},
            "support": {
                "threshold_q99": 1.5,
                "audit_coverage": 0.9,
                "challenge_scores": {"negative": 5.0},
                "challenge_accepted": {"negative": False},
            },
            "full_trajectory_holdout": {
                "teacher_samples": 10,
                "all_steps": {"tissue_mae": 0.12, "gc_percentage_point_mae": 0.23},
                "late_steps_21_100": {"tissue_mae": 0.13},
                "support_coverage_all_steps": 0.8,
            },
            "benchmark": {"scoring_speedup": 1.5},
            "injected_full_comparison": {
                "chains": 2,
                "original_seconds": 4.0,
                "surrogate_seconds": 2.0,
                "end_to_end_speedup": 2.0,
                "identical_final_sequences": 2,
                "max_final_energy_difference": 0.01,
            },
        },
    )
    _write_json(analysis / "other_examples_audit.json", {"collection_count": 1})
    _write_json(
        tmp_path / "data" / "visualizations" / "manifest.json",
        {
            "candidates": [
                {
                    "candidate_id": "curated:smoke:final",
                    "fixture": "curated",
                    "tier": "smoke",
                    "artifact_role": "final",
                    "complete": True,
                    "segment_label": "candidate",
                    "sequence": {"type": "protein", "value": "CURATEDSEQ"},
                    "score_vector": [],
                    "structure_ids": [],
                }
            ],
            "structures": [],
            "molecules": [],
            "gaps": [],
        },
    )
    _write_json(
        tmp_path / "workspaces" / "phillip" / "fixtures" / "demo" / "methodology.json",
        {
            "paper": {"source_path": "data/papers/demo.txt"},
            "constraints": [{"evidence": [{"quote": "aggregate only"}]}],
        },
    )
    checkpoint = tmp_path / "data" / "runs" / "checkpoints" / "demo" / "full"
    _write_json(
        checkpoint / "manifest.json",
        {"status": "completed", "resume_count": 1},
    )
    _write_json(
        checkpoint / "program-0000.json",
        {
            "stages": {
                "0": {"planned_units": 5, "completed_units": 5},
            }
        },
    )
    (checkpoint / "program-0000.trace.jsonl").write_text('{"step": 1}\n{"step": 5}\n')

    output = tmp_path / "portable-report.html"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--output",
            str(output),
            "--strict",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = output.read_text()
    assert "portable interactive report" in report
    assert "Why ProtoFuse" in report
    assert "What the current results show" in report
    assert "What blocks the next claim" in report
    assert "What to measure next" in report
    assert "Surrogate performance" in report
    assert "CURATED VISUALIZATION BUNDLE" in report
    assert "CURATEDSEQ" in report
    assert "training loss" in report
    assert "classification accuracy" in report
    assert "How trajectories become model splits" in report
    assert "One seed creates one trajectory" in report
    assert "60 train + 20 calibration + 20 untouched test trajectories" in report
    assert 'data-tab="routing"' in report
    assert "2.000×" in report
    assert "ESM-2 protein maturation" in report
    assert "MUST_NOT_APPEAR_IN_REPORT" not in report
    assert "<script src=" not in report
    assert "<link " not in report
    assert "https://" not in report
    assert "http://" not in report

    match = re.search(
        r'<script type="application/json" id="protofuse-report-data">(.*?)</script>',
        report,
    )
    assert match is not None
    embedded = json.loads(match.group(1))
    assert embedded["summary"]["full_model_baselines"] == 1
    assert embedded["summary"]["constraints_with_evidence"] == 1
    assert embedded["checkpoints"]["run_count"] == 1
    assert embedded["checkpoints"]["resume_count"] == 1
    assert embedded["checkpoints"]["completed_units"] == 5
    assert embedded["checkpoints"]["trace_rows"] == 2
    assert embedded["pilot"]["audit"]["tissue_mae"] == 0.1
    assert embedded["pilot"]["support"]["audit_coverage"] == 0.9
    assert embedded["pilot"]["classification_accuracy"] is None


def test_slides_deck_is_self_contained_and_16_9(tmp_path: Path) -> None:
    analysis = tmp_path / "data" / "analysis"
    _write_json(
        analysis / "modal_smoke_summary.json",
        {
            "recorded_at": "2026-08-15",
            "runs": [
                {
                    "fixture": "esm2-protein-maturation",
                    "tier": "smoke",
                    "status": "ok",
                    "num_steps": 5,
                    "wall_seconds": 12.5,
                }
            ],
        },
    )
    _write_json(
        analysis / "custom-egfp-lung" / "surrogate_pilot_report.json",
        {
            "teacher_samples": 10,
            "teacher_collection_seconds": 1.25,
            "splits": {"train": 6, "calibration": 2, "audit": 2},
            "calibration": {"tissue_mae": 0.11, "gc_percentage_point_mae": 0.22},
            "audit": {"tissue_mae": 0.1, "gc_percentage_point_mae": 0.2},
            "support": {
                "threshold_q99": 1.5,
                "audit_coverage": 0.9,
                "challenge_scores": {"negative": 5.0},
                "challenge_accepted": {"negative": False},
            },
            "full_trajectory_holdout": {
                "teacher_samples": 10,
                "all_steps": {"tissue_mae": 0.12, "gc_percentage_point_mae": 0.23},
                "late_steps_21_100": {"tissue_mae": 0.13},
                "support_coverage_all_steps": 0.8,
            },
            "benchmark": {"scoring_speedup": 1.5},
            "injected_full_comparison": {
                "chains": 2,
                "original_seconds": 4.0,
                "surrogate_seconds": 2.0,
                "end_to_end_speedup": 2.0,
                "identical_final_sequences": 2,
                "max_final_energy_difference": 0.01,
            },
        },
    )
    _write_json(
        tmp_path / "data" / "visualizations" / "manifest.json",
        {
            "candidates": [
                {
                    "candidate_id": "curated:smoke:final",
                    "fixture": "curated",
                    "tier": "smoke",
                    "artifact_role": "final",
                    "complete": True,
                    "segment_label": "candidate",
                    "sequence": {"type": "protein", "value": "CURATEDSEQ"},
                    "score_vector": [],
                    "structure_ids": [],
                }
            ],
            "structures": [],
            "molecules": [],
            "gaps": [],
        },
    )
    _write_json(
        tmp_path / "workspaces" / "phillip" / "fixtures" / "demo" / "methodology.json",
        {
            "paper": {"source_path": "data/papers/demo.txt"},
            "constraints": [{"evidence": [{"quote": "aggregate only"}]}],
        },
    )

    output = tmp_path / "evaluation-slides.html"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--output",
            str(output),
            "--slides",
            "--strict",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = output.read_text()
    slide_count = report.count('class="slide"')
    assert slide_count >= 5
    assert "1920px" in report
    assert "1080px" in report
    assert "aspect-ratio:16/9" in report.replace(" ", "")
    assert "Why ProtoFuse" in report
    assert "Routing concept" in report
    assert "Current evidence summary" in report
    assert "What the pilot establishes" in report
    assert "Surrogate performance" in report
    assert "Curated visualization bundle" in report
    assert "Sai Thatigotla and Philip Thomas" in report
    assert "<h1>ProtoFuse</h1>" in report
    assert "PROMISING / UNPROVEN" not in report
    assert "What blocks the next claim" in report
    assert "What to measure next" in report
    assert "Evidence appendix summary" in report
    assert "Full-model benchmark summaries" in report
    assert "PROTOFUSE / EVALUATION ·" in report
    assert "<script src=" not in report
    assert "<link " not in report
    assert "https://" not in report


def test_pdf_export_requires_playwright_or_writes_pdf(tmp_path: Path) -> None:
    analysis = tmp_path / "data" / "analysis"
    _write_json(
        analysis / "modal_smoke_summary.json",
        {"recorded_at": "2026-08-15", "runs": []},
    )
    _write_json(
        analysis / "custom-egfp-lung" / "surrogate_pilot_report.json",
        {
            "teacher_samples": 1,
            "splits": {"train": 1, "calibration": 0, "audit": 0},
            "calibration": {},
            "audit": {},
            "support": {"challenge_accepted": {}, "challenge_scores": {}},
        },
    )
    _write_json(
        tmp_path / "data" / "visualizations" / "manifest.json",
        {"candidates": [], "structures": [], "molecules": [], "gaps": []},
    )

    output = tmp_path / "evaluation-slides.pdf"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--output",
            str(output),
            "--pdf",
            "--strict",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        assert "playwright" in completed.stderr.lower()
        return

    assert output.is_file()
    assert output.read_bytes()[:4] == b"%PDF"


def test_static_report_strict_mode_rejects_missing_primary_results(tmp_path: Path) -> None:
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

    assert completed.returncode != 0
    assert "missing required result artifacts" in completed.stderr
