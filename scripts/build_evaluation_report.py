#!/usr/bin/env python3
# ruff: noqa: E501 -- the self-contained HTML/CSS template intentionally stays literal
"""Build a self-contained ProtoFuse evaluation report from local result artifacts."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "1.0"

OBJECTIVES = {
    "antibody-cdr-maturation": "AbLang NLL + ipTM gates",
    "boltz2-state-sweep": "State RMSD + mean pLDDT",
    "esm2-protein-maturation": "ESM-2 perplexity + pLDDT / PAE",
    "rfdiffusion3-boltz2-binder": "ipTM + binding strength + quality gates",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _source_record(path: Path, root: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        display_path = str(path.relative_to(root))
    except ValueError:
        display_path = path.name
    return {
        "path": display_path,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def _fixture_label(fixture: str) -> str:
    labels = {
        "antibody-cdr-maturation": "Antibody CDR maturation",
        "boltz2-state-sweep": "Boltz-2 state sweep",
        "esm2-protein-maturation": "ESM-2 protein maturation",
        "rfdiffusion3-boltz2-binder": "RFdiffusion3 + Boltz-2 binder",
    }
    return labels.get(fixture, fixture.replace("-", " ").title())


def _paper_source_kind(paper: dict[str, Any]) -> str:
    source_path = paper.get("source_path")
    identifier = paper.get("identifier")
    if isinstance(source_path, str) and source_path not in {
        None,
        "",
        "docs/CANDIDATE_WORKFLOWS.md",
    }:
        return "paper text"
    if isinstance(identifier, str) and identifier.startswith("10."):
        return "registered DOI"
    if source_path == "docs/CANDIDATE_WORKFLOWS.md":
        return "internal spec"
    return "no paper anchor"


def _paper_study_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted((root / "workspaces" / "phillip" / "fixtures").glob("*/methodology.json")):
        methodology = _read_json(path)
        if methodology is None:
            continue
        paper = methodology.get("paper", {})
        if not isinstance(paper, dict):
            paper = {}
        fixture_id = path.parent.name
        identifier = paper.get("identifier")
        source_kind = _paper_source_kind(paper)
        if isinstance(identifier, str) and identifier.startswith("10."):
            identifier_label = identifier
        elif isinstance(paper.get("source_path"), str) and paper["source_path"]:
            identifier_label = str(paper["source_path"]).split("/")[-1]
        elif isinstance(identifier, str) and identifier:
            identifier_label = identifier
        else:
            identifier_label = "not recorded"
        rows.append(
            {
                "fixture": fixture_id,
                "workload": _fixture_label(fixture_id),
                "paper_title": str(paper.get("title") or _fixture_label(fixture_id)),
                "identifier": identifier_label,
                "source_kind": source_kind,
            }
        )
    return rows


def _methodology_summary(root: Path) -> dict[str, Any]:
    paths = sorted((root / "workspaces" / "phillip" / "fixtures").glob("*/methodology.json"))
    constraint_count = 0
    constraints_with_evidence = 0
    paper_source_count = 0
    sources: list[dict[str, str]] = []
    for path in paths:
        methodology = _read_json(path)
        if methodology is None:
            continue
        constraints = methodology.get("constraints", [])
        if isinstance(constraints, list):
            constraint_count += len(constraints)
            constraints_with_evidence += sum(
                1
                for constraint in constraints
                if isinstance(constraint, dict) and constraint.get("evidence")
            )
        paper = methodology.get("paper", {})
        source_path = paper.get("source_path") if isinstance(paper, dict) else None
        if isinstance(source_path, str) and source_path != "docs/CANDIDATE_WORKFLOWS.md":
            paper_source_count += 1
        record = _source_record(path, root)
        if record is not None:
            sources.append(record)
    return {
        "fixture_count": len(paths),
        "constraint_count": constraint_count,
        "constraints_with_evidence": constraints_with_evidence,
        "paper_source_count": paper_source_count,
        "sources": sources,
    }


def _checkpoint_summary(checkpoint_root: Path, root: Path) -> dict[str, Any]:
    manifests = sorted(checkpoint_root.glob("*/*/manifest.json"))
    statuses: Counter[str] = Counter()
    resume_count = 0
    planned_units = 0
    completed_units = 0
    trace_rows = 0
    sources: list[dict[str, str]] = []
    for manifest_path in manifests:
        manifest = _read_json(manifest_path)
        if manifest is None:
            continue
        statuses[str(manifest.get("status", "unknown"))] += 1
        resume_count += int(manifest.get("resume_count", 0) or 0)
        record = _source_record(manifest_path, root)
        if record is not None:
            sources.append(record)
        for program_path in sorted(manifest_path.parent.glob("program-*.json")):
            program = _read_json(program_path)
            if program is None:
                continue
            stages = program.get("stages", {})
            if isinstance(stages, dict):
                for stage in stages.values():
                    if isinstance(stage, dict):
                        planned_units += int(stage.get("planned_units", 0) or 0)
                        completed_units += int(stage.get("completed_units", 0) or 0)
            program_source = _source_record(program_path, root)
            if program_source is not None:
                sources.append(program_source)
        for trace_path in sorted(manifest_path.parent.glob("program-*.trace.jsonl")):
            with trace_path.open(encoding="utf-8") as handle:
                trace_rows += sum(1 for line in handle if line.strip())
            trace_source = _source_record(trace_path, root)
            if trace_source is not None:
                sources.append(trace_source)
    return {
        "run_count": len(manifests),
        "statuses": dict(statuses),
        "resume_count": resume_count,
        "planned_units": planned_units,
        "completed_units": completed_units,
        "trace_rows": trace_rows,
        "sources": sources,
    }


def _benchmark_rows(
    modal: dict[str, Any] | None,
    pilot: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if pilot is not None:
        comparison = pilot.get("injected_full_comparison", {})
        audit = pilot.get("audit", {})
        if isinstance(comparison, dict) and comparison:
            tissue_mae = _number(audit.get("tissue_mae")) if isinstance(audit, dict) else None
            gc_mae = (
                _number(audit.get("gc_percentage_point_mae"))
                if isinstance(audit, dict)
                else None
            )
            error = " · ".join(
                part
                for part in (
                    f"{tissue_mae:.3g} tissue MAE" if tissue_mae is not None else "",
                    f"{gc_mae:.3g} pp GC MAE" if gc_mae is not None else "",
                )
                if part
            )
            rows.append(
                {
                    "workload": "CUSTOM eGFP lung",
                    "tier": "full · injected pilot",
                    "work": (
                        f"{comparison.get('chains', 'unknown')} chains × 100 iterations"
                    ),
                    "full_seconds": _number(comparison.get("original_seconds")),
                    "fused_seconds": _number(comparison.get("surrogate_seconds")),
                    "objective": "Tissue codon score + GC%",
                    "objective_error": error or "not available",
                    "status": "paired experimental",
                    "note": (
                        "Experimental injection only; it is not a registered FusionBundle "
                        "and the support gate is not wired into routing."
                    ),
                }
            )
    if modal is not None:
        runs = modal.get("runs", [])
        if isinstance(runs, list):
            for run in runs:
                if not isinstance(run, dict):
                    continue
                fixture = str(run.get("fixture", "unknown"))
                steps = _int(run.get("num_steps"))
                samples = _int(run.get("num_samples"))
                results = _int(run.get("num_results"))
                if steps is not None:
                    work = f"{steps} optimizer units"
                elif samples is not None:
                    suffix = f" · {results} retained" if results is not None else ""
                    work = f"{samples} samples{suffix}"
                else:
                    work = "not recorded"
                rows.append(
                    {
                        "workload": _fixture_label(fixture),
                        "tier": f"{run.get('tier', 'unknown')} · Modal",
                        "work": work,
                        "full_seconds": _number(run.get("wall_seconds")),
                        "fused_seconds": None,
                        "objective": OBJECTIVES.get(fixture, "not recorded"),
                        "objective_error": "Not computed against paper objective",
                        "status": str(run.get("status", "unknown")),
                        "note": "Original full-model path; no paired learned-fusion run is present.",
                    }
                )
    return rows


def collect_report_data(
    root: Path,
    *,
    analysis_dir: Path,
    checkpoint_dir: Path,
) -> dict[str, Any]:
    modal_path = analysis_dir / "modal_smoke_summary.json"
    pilot_path = analysis_dir / "custom-egfp-lung" / "surrogate_pilot_report.json"
    audit_path = analysis_dir / "other_examples_audit.json"
    visualization_path = root / "data" / "visualizations" / "manifest.json"
    modal = _read_json(modal_path)
    pilot = _read_json(pilot_path)
    collection_audit = _read_json(audit_path)
    visualizations = _read_json(visualization_path)
    methodology = _methodology_summary(root)
    paper_studies = _paper_study_rows(root)
    checkpoints = _checkpoint_summary(checkpoint_dir, root)

    sources = [
        record
        for record in (
            _source_record(modal_path, root),
            _source_record(pilot_path, root),
            _source_record(audit_path, root),
            _source_record(visualization_path, root),
        )
        if record is not None
    ]
    sources.extend(methodology.pop("sources"))
    sources.extend(checkpoints.pop("sources"))

    splits = pilot.get("splits", {}) if pilot is not None else {}
    trajectory = pilot.get("full_trajectory_holdout", {}) if pilot is not None else {}
    support = pilot.get("support", {}) if pilot is not None else {}
    challenges = support.get("challenge_accepted", {}) if isinstance(support, dict) else {}
    negative_count = len(challenges) if isinstance(challenges, dict) else 0
    pilot_benchmark = pilot.get("benchmark", {}) if pilot is not None else {}
    injected_full = pilot.get("injected_full_comparison", {}) if pilot is not None else {}
    pilot_audit = pilot.get("audit", {}) if pilot is not None else {}
    pilot_calibration = pilot.get("calibration", {}) if pilot is not None else {}
    pilot_trajectory = (
        pilot.get("full_trajectory_holdout", {}) if pilot is not None else {}
    )
    collection_count = (
        int(collection_audit.get("collection_count", 0))
        if collection_audit is not None
        else 0
    )
    modal_runs = modal.get("runs", []) if modal is not None else []
    baseline_count = len(modal_runs) if isinstance(modal_runs, list) else 0
    audit_date = (
        str(modal.get("recorded_at"))
        if modal is not None and modal.get("recorded_at")
        else datetime.now(UTC).date().isoformat()
    )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "audit_date": audit_date,
        "summary": {
            "full_model_baselines": baseline_count,
            "experimental_surrogates": 1 if pilot is not None else 0,
            "registered_surrogates": 0,
            "joint_objectives": 2 if pilot is not None else 0,
            "paired_gpu_comparisons": 0,
            "negative_challenges": negative_count,
            "positive_holdout": 0,
            "reviewed_collections_audited": collection_count,
            **methodology,
        },
        "checkpoints": checkpoints,
        "paper_studies": paper_studies,
        "splits": {
            "train": int(splits.get("train", 0)) if isinstance(splits, dict) else 0,
            "calibration": (
                int(splits.get("calibration", 0)) if isinstance(splits, dict) else 0
            ),
            "audit": int(splits.get("audit", 0)) if isinstance(splits, dict) else 0,
            "full_trajectory": (
                int(trajectory.get("teacher_samples", 0))
                if isinstance(trajectory, dict)
                else 0
            ),
            "negative_ood": negative_count,
            "positive": 0,
            "positive_uncertain": 0,
        },
        "pilot": {
            "model_family": "multi-output ordinary least squares",
            "objective_count": 2 if pilot is not None else 0,
            "teacher_samples": int(pilot.get("teacher_samples", 0)) if pilot else 0,
            "teacher_collection_seconds": (
                _number(pilot.get("teacher_collection_seconds")) if pilot else None
            ),
            "training_loss": None,
            "validation_loss": None,
            "classification_accuracy": None,
            "scoring_speedup": (
                _number(pilot_benchmark.get("scoring_speedup"))
                if isinstance(pilot_benchmark, dict)
                else None
            ),
            "end_to_end_speedup": (
                _number(injected_full.get("end_to_end_speedup"))
                if isinstance(injected_full, dict)
                else None
            ),
            "identical_final_sequences": (
                _int(injected_full.get("identical_final_sequences"))
                if isinstance(injected_full, dict)
                else None
            ),
            "comparison_chains": (
                _int(injected_full.get("chains"))
                if isinstance(injected_full, dict)
                else None
            ),
            "max_final_energy_difference": (
                _number(injected_full.get("max_final_energy_difference"))
                if isinstance(injected_full, dict)
                else None
            ),
            "tissue_mae": (
                _number(pilot_audit.get("tissue_mae"))
                if isinstance(pilot_audit, dict)
                else None
            ),
            "gc_percentage_point_mae": (
                _number(pilot_audit.get("gc_percentage_point_mae"))
                if isinstance(pilot_audit, dict)
                else None
            ),
            "calibration": {
                key: _number(pilot_calibration.get(key))
                if isinstance(pilot_calibration, dict)
                else None
                for key in (
                    "tissue_mae",
                    "tissue_max_error",
                    "gc_percentage_point_mae",
                    "gc_percentage_point_max_error",
                )
            },
            "audit": {
                key: _number(pilot_audit.get(key))
                if isinstance(pilot_audit, dict)
                else None
                for key in (
                    "tissue_mae",
                    "tissue_max_error",
                    "gc_percentage_point_mae",
                    "gc_percentage_point_max_error",
                )
            },
            "trajectory": {
                "teacher_samples": (
                    _int(pilot_trajectory.get("teacher_samples"))
                    if isinstance(pilot_trajectory, dict)
                    else None
                ),
                "all_steps": (
                    pilot_trajectory.get("all_steps", {})
                    if isinstance(pilot_trajectory, dict)
                    else {}
                ),
                "late_steps": (
                    pilot_trajectory.get("late_steps_21_100", {})
                    if isinstance(pilot_trajectory, dict)
                    else {}
                ),
                "support_coverage_all_steps": (
                    _number(pilot_trajectory.get("support_coverage_all_steps"))
                    if isinstance(pilot_trajectory, dict)
                    else None
                ),
                "support_coverage_late_steps": (
                    _number(pilot_trajectory.get("support_coverage_late_steps"))
                    if isinstance(pilot_trajectory, dict)
                    else None
                ),
            },
            "support": {
                "threshold_q99": (
                    _number(support.get("threshold_q99"))
                    if isinstance(support, dict)
                    else None
                ),
                "audit_coverage": (
                    _number(support.get("audit_coverage"))
                    if isinstance(support, dict)
                    else None
                ),
                "challenge_scores": (
                    support.get("challenge_scores", {})
                    if isinstance(support, dict)
                    else {}
                ),
                "challenge_accepted": challenges if isinstance(challenges, dict) else {},
            },
        },
        "visualizations": visualizations
        or {
            "candidates": [],
            "structures": [],
            "molecules": [],
            "gaps": [],
        },
        "benchmarks": _benchmark_rows(modal, pilot),
        "sources": sources,
    }


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _format_time(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return "not run"
    if seconds < 10:
        return f"{seconds:.3f} s"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.0f}s"


def _metric(value: Any, label: str, detail: str) -> str:
    return (
        '<article class="metric">'
        f'<div class="metric-value">{_escape(value)}</div>'
        f'<div class="metric-label">{_escape(label)}</div>'
        f'<p>{_escape(detail)}</p>'
        "</article>"
    )


def _state(label: str, kind: str) -> str:
    return f'<span class="state {kind}">{_escape(label)}</span>'


def _render_benchmarks(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<div class="empty">No benchmark summaries were supplied.</div>'
    rendered = []
    for row in rows:
        fused = row.get("fused_seconds")
        rendered.append(
            "<details class=\"benchmark\">"
            "<summary>"
            f'<span class="workload"><strong>{_escape(row["workload"])}</strong>'
            f'<small>{_escape(row["tier"])}</small></span>'
            f'<span>{_escape(row["work"])}</span>'
            f'<span class="mono">{_escape(_format_time(row.get("full_seconds")))}</span>'
            f'<span class="mono {"good" if fused is not None else "muted"}">'
            f'{_escape(_format_time(fused))}</span>'
            f'<span>{_escape(row["objective_error"])}</span>'
            "</summary>"
            '<div class="benchmark-detail">'
            f'<div><span>Objective</span><strong>{_escape(row["objective"])}</strong></div>'
            f'<div><span>Status</span><strong>{_escape(row["status"])}</strong></div>'
            f'<div><span>Interpretation</span><strong>{_escape(row["note"])}</strong></div>'
            "</div></details>"
        )
    return "".join(rendered)


def _format_speedup(value: Any) -> str:
    return f"{value:.3f}×" if isinstance(value, (int, float)) else "not available"


def _format_error(value: Any, unit: str = "") -> str:
    return f"{value:.3g}{unit}" if isinstance(value, (int, float)) else "not available"


def _format_percent(value: Any) -> str:
    return f"{100 * value:.1f}%" if isinstance(value, (int, float)) else "not available"


def _render_pilot(pilot: dict[str, Any]) -> str:
    chains = pilot.get("comparison_chains")
    identical = pilot.get("identical_final_sequences")
    sequence_result = (
        f"{identical} / {chains}"
        if isinstance(chains, int) and isinstance(identical, int)
        else "not available"
    )
    results = [
        (
            _format_speedup(pilot.get("scoring_speedup")),
            "parent-scoring speedup",
            "Feature extraction plus two-output prediction versus the two CPU objectives.",
        ),
        (
            _format_speedup(pilot.get("end_to_end_speedup")),
            "end-to-end speedup",
            "Observed across the injected 20-chain full pilot; orchestration limits the gain.",
        ),
        (
            sequence_result,
            "identical final sequences",
            "This checks the narrow pilot outcome, not generalization to new objectives or models.",
        ),
        (
            _format_error(pilot.get("max_final_energy_difference")),
            "maximum final-energy difference",
            "The joint linear surrogate is effectively exact for these two simple objectives.",
        ),
    ]
    cards = "".join(
        '<article class="result-card">'
        f'<strong>{_escape(value)}</strong><span>{_escape(label)}</span><p>{_escape(detail)}</p>'
        "</article>"
        for value, label, detail in results
    )
    return (
        '<div class="result-intro"><div><span class="kicker">WHAT THE PILOT ESTABLISHES</span>'
        '<h3>A joint surrogate can reproduce two base-composition objectives.</h3></div>'
        '<p>The CUSTOM experiment fits one ordinary least-squares matrix to tissue codon score '
        'and GC fraction. It is a useful instrumentation proof, but neither objective is an '
        'expensive GPU parent model and no FusionBundle is registered.</p></div>'
        f'<div class="result-grid">{cards}</div>'
    )


def _surrogate_metric_card(value: str, label: str, note: str) -> str:
    return (
        '<article class="surrogate-metric">'
        f'<strong>{_escape(value)}</strong><span>{_escape(label)}</span>'
        f'<p>{_escape(note)}</p></article>'
    )


def _render_surrogate_metrics(pilot: dict[str, Any]) -> str:
    calibration = pilot.get("calibration", {})
    audit = pilot.get("audit", {})
    trajectory = pilot.get("trajectory", {})
    support = pilot.get("support", {})
    challenges = support.get("challenge_accepted", {}) if isinstance(support, dict) else {}
    scores = support.get("challenge_scores", {}) if isinstance(support, dict) else {}
    if not isinstance(scores, dict):
        scores = {}
    rejected = (
        sum(not bool(value) for value in challenges.values())
        if isinstance(challenges, dict)
        else 0
    )


    challenge_count = len(challenges) if isinstance(challenges, dict) else 0

    model_cards = "".join(
        (
            _surrogate_metric_card(
                str(pilot.get("model_family", "not recorded")),
                "model",
                "One fitted matrix jointly predicts both objectives.",
            ),
            _surrogate_metric_card(
                "not recorded",
                "training loss",
                "The artifact does not persist a fitted loss value or learning curve.",
            ),
            _surrogate_metric_card(
                "not recorded",
                "validation loss",
                "A calibration split and MAE are present, but no scalar validation loss is stored.",
            ),
            _surrogate_metric_card(
                "not applicable",
                "classification accuracy",
                "This pilot is a regression model; routing classification needs positive holdouts.",
            ),
        )
    )

    calibration_cards = "".join(
        (
            _surrogate_metric_card(
                _format_error(calibration.get("tissue_mae")),
                "tissue-score MAE",
                "Calibration split.",
            ),
            _surrogate_metric_card(
                _format_error(calibration.get("tissue_max_error")),
                "tissue max error",
                "Calibration split.",
            ),
            _surrogate_metric_card(
                _format_error(calibration.get("gc_percentage_point_mae"), " pp"),
                "GC MAE",
                "Percentage-point error on the calibration split.",
            ),
            _surrogate_metric_card(
                _format_error(calibration.get("gc_percentage_point_max_error"), " pp"),
                "GC max error",
                "Percentage-point error on the calibration split.",
            ),
        )
    )
    audit_cards = "".join(
        (
            _surrogate_metric_card(
                _format_error(audit.get("tissue_mae")),
                "tissue-score MAE",
                "Held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_error(audit.get("tissue_max_error")),
                "tissue max error",
                "Held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_error(audit.get("gc_percentage_point_mae"), " pp"),
                "GC MAE",
                "Percentage-point error on the held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_error(audit.get("gc_percentage_point_max_error"), " pp"),
                "GC max error",
                "Percentage-point error on the held-out audit split.",
            ),
        )
    )
    all_steps = trajectory.get("all_steps", {}) if isinstance(trajectory, dict) else {}
    late_steps = trajectory.get("late_steps", {}) if isinstance(trajectory, dict) else {}
    trajectory_samples = trajectory.get("teacher_samples")
    trajectory_sample_label = (
        f"{trajectory_samples:,}" if isinstance(trajectory_samples, int) else "unknown"
    )
    trajectory_cards = "".join(
        (
            _surrogate_metric_card(
                _format_error(all_steps.get("tissue_mae")),
                "all-step tissue MAE",
                f"{trajectory_sample_label} held-out trajectory labels.",
            ),
            _surrogate_metric_card(
                _format_error(late_steps.get("tissue_mae")),
                "late-step tissue MAE",
                "Steps 21–100 test the region visited later in optimization.",
            ),
            _surrogate_metric_card(
                _format_error(all_steps.get("gc_percentage_point_mae"), " pp"),
                "all-step GC MAE",
                "Held-out full trajectories.",
            ),
            _surrogate_metric_card(
                _format_percent(trajectory.get("support_coverage_all_steps")),
                "trajectory gate coverage",
                "Coverage alone is not safety; accepted positive accuracy is still missing.",
            ),
        )
    )
    challenge_rows = "".join(
        '<tr>'
        f'<td>{_escape(name.replace("_", " "))}</td>'
        f'<td class="mono">{_escape(_format_error(scores.get(name)))}</td>'
        f'<td>{_state("accepted" if accepted else "rejected", "missing" if accepted else "available")}</td>'
        "</tr>"
        for name, accepted in challenges.items()
    ) or '<tr><td colspan="3">No routing challenges recorded.</td></tr>'
    routing_cards = "".join(
        (
            _surrogate_metric_card(
                _format_percent(support.get("audit_coverage")),
                "audit coverage",
                "Fraction of in-domain audit samples accepted by the support gate.",
            ),
            _surrogate_metric_card(
                f"{rejected} / {challenge_count}",
                "negative challenges rejected",
                "Useful specificity evidence, but the sample is small and hand-crafted.",
            ),
            _surrogate_metric_card(
                "0 samples",
                "positive routing holdout",
                "Sensitivity / false-deferral rate cannot yet be calculated.",
            ),
            _surrogate_metric_card(
                _format_error(support.get("threshold_q99")),
                "support threshold q99",
                "Frozen threshold recorded by the pilot artifact.",
            ),
        )
    )

    return (
        '<div class="surrogate-header"><div><span class="kicker">MODEL CARD · CUSTOM eGFP LUNG</span>'
        '<h3>Surrogate performance, with missing metrics made explicit.</h3></div>'
        f'<p>{pilot.get("teacher_samples", 0):,} teacher labels · '
        f'{_format_time(pilot.get("teacher_collection_seconds"))} collection · '
        f'{pilot.get("objective_count", 0)} joint objectives</p></div>'
        f'<div class="surrogate-model-grid">{model_cards}</div>'
        '<div class="tabs" data-tab-group="surrogate">'
        '<div class="tab-list" role="tablist" aria-label="Surrogate evaluation cohorts">'
        '<button class="tab active" type="button" data-tab="audit">Audit</button>'
        '<button class="tab" type="button" data-tab="calibration">Calibration</button>'
        '<button class="tab" type="button" data-tab="trajectory">Trajectory</button>'
        '<button class="tab" type="button" data-tab="routing">Routing</button></div>'
        f'<div class="tab-panel active" data-panel="audit"><div class="surrogate-grid">{audit_cards}</div></div>'
        f'<div class="tab-panel" data-panel="calibration"><div class="surrogate-grid">{calibration_cards}</div></div>'
        f'<div class="tab-panel" data-panel="trajectory"><div class="surrogate-grid">{trajectory_cards}</div></div>'
        f'<div class="tab-panel" data-panel="routing"><div class="surrogate-grid">{routing_cards}</div>'
        '<table class="challenge-table"><thead><tr><th>Challenge</th><th>OOD score</th><th>Gate</th></tr></thead>'
        f'<tbody>{challenge_rows}</tbody></table></div></div>'
        '<p class="metric-note"><strong>Metric interpretation:</strong> MAE and maximum error are '
        'appropriate for these continuous outputs. “Accuracy” would only be meaningful for the '
        'accept / defer router, and cannot be reported until positive and uncertain-positive '
        'holdouts exist.</p>'
    )


def _residue_class(residue: str, sequence_type: str) -> str:
    residue = residue.upper()
    if sequence_type == "dna":
        return {"A": "base-a", "C": "base-c", "G": "base-g", "T": "base-t"}.get(
            residue, "residue-other"
        )
    for group, class_name in (
        ("AILMFWVY", "residue-hydrophobic"),
        ("KRH", "residue-positive"),
        ("DE", "residue-negative"),
        ("STNQ", "residue-polar"),
        ("CGP", "residue-special"),
    ):
        if residue in group:
            return class_name
    return "residue-other"


def _render_visualization_assets(visualizations: dict[str, Any]) -> str:
    candidates = visualizations.get("candidates", [])
    structures = visualizations.get("structures", [])
    molecules = visualizations.get("molecules", [])
    gaps = visualizations.get("gaps", [])
    if not isinstance(candidates, list) or not candidates:
        return '<div class="empty">No curated visualization bundle is available.</div>'
    structure_by_id = (
        {
            item.get("structure_id"): item
            for item in structures
            if isinstance(item, dict) and isinstance(item.get("structure_id"), str)
        }
        if isinstance(structures, list)
        else {}
    )
    summary = (
        '<div class="artifact-summary">'
        f'<div><strong>{len(candidates)}</strong><span>sequence artifacts</span></div>'
        f'<div><strong>{len(structures) if isinstance(structures, list) else 0}</strong>'
        '<span>structure artifacts</span></div>'
        f'<div><strong>{len(molecules) if isinstance(molecules, list) else 0}</strong>'
        '<span>molecule artifacts</span></div></div>'
    )
    cards: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        sequence = candidate.get("sequence", {})
        if not isinstance(sequence, dict):
            continue
        value = sequence.get("value")
        sequence_type = str(sequence.get("type", "unknown"))
        if not isinstance(value, str) or not value:
            continue
        residues = "".join(
            f'<span class="residue {_residue_class(residue, sequence_type)}">'
            f"{_escape(residue)}</span>"
            for residue in value
        )
        complete = bool(candidate.get("complete"))
        completeness = _state(
            "complete" if complete else "partial",
            "available" if complete else "partial",
        )
        score_vector = candidate.get("score_vector", [])
        score_text = (
            " · ".join(
                (
                    f'{item.get("name")}: {_format_error(item.get("value"))} '
                    f'{item.get("units", "")}'
                ).strip()
                for item in score_vector
                if isinstance(item, dict)
            )
            or "No final score vector recorded"
        )
        structure_links: list[str] = []
        structure_ids = candidate.get("structure_ids", [])
        if isinstance(structure_ids, list):
            for structure_id in structure_ids:
                structure = structure_by_id.get(structure_id)
                if not isinstance(structure, dict) or not isinstance(
                    structure.get("path"), str
                ):
                    continue
                structure_links.append(
                    f'<a href="../data/visualizations/{_escape(structure["path"])}">'
                    f'{_escape(structure.get("role", "structure"))} · '
                    f'{_escape(structure.get("format", "file"))}</a>'
                )
        links = " · ".join(structure_links) or "No saved structure"
        role = str(candidate.get("artifact_role", "unknown"))
        cards.append(
            '<article class="artifact-card"><div class="artifact-head"><div>'
            f'<span class="kicker">{_escape(candidate.get("fixture", "unknown"))} · '
            f'{_escape(candidate.get("tier", "unknown"))}</span>'
            f'<h3>{_escape(candidate.get("segment_label", "construct"))}</h3></div>'
            f'{completeness}</div><div class="artifact-meta">'
            f'<span>{_escape(sequence_type)}</span><span>{len(value):,} residues / bases</span>'
            f'<span>{_escape(role.replace("_", " "))}</span></div>'
            '<details class="sequence-view"><summary>Inspect saved sequence</summary>'
            f'<div class="sequence-track mono">{residues}</div></details>'
            f'<p><strong>Scores:</strong> {_escape(score_text)}</p>'
            f'<p><strong>Structure:</strong> {links}</p></article>'
        )
    gap_html = "".join(
        f'<li><strong>{_escape(gap.get("code", "gap"))}</strong> — '
        f'{_escape(gap.get("message", ""))}</li>'
        for gap in gaps
        if isinstance(gap, dict)
    )
    return (
        '<div class="artifact-intro"><div><span class="kicker">CURATED VISUALIZATION BUNDLE</span>'
        '<h3>Saved design outputs, not screenshots.</h3></div><p>Sequences are embedded for '
        'direct inspection. Structure and future molecule files remain versioned assets with '
        'stable identifiers and hashes.</p></div>'
        f"{summary}<div class=\"artifact-grid\">{''.join(cards)}</div>"
        f'<div class="artifact-gaps"><strong>Still missing</strong><ul>{gap_html}</ul></div>'
    )


def _gap_card(
    index: int,
    title: str,
    evidence: str,
    measurement: str,
    priority: str,
) -> str:
    return (
        '<article class="gap-card">'
        f'<div class="gap-meta"><span>G{index:02d}</span><b>{_escape(priority)}</b></div>'
        f'<h3>{_escape(title)}</h3>'
        f'<p><strong>Current evidence:</strong> {_escape(evidence)}</p>'
        f'<p><strong>Measure next:</strong> {_escape(measurement)}</p>'
        "</article>"
    )


def _render_gaps(summary: dict[str, Any], checkpoints: dict[str, Any]) -> str:
    return "".join(
        _gap_card(index, title, evidence, measurement, priority)
        for index, (title, evidence, measurement, priority) in enumerate(
            _gap_definitions(summary, checkpoints), start=1
        )
    )


def _render_measurement_plan() -> str:
    return "".join(
        '<article class="plan-row">'
        f'<span class="plan-index">{index:02d}</span><div>'
        f"<h3>{_escape(item)}</h3></div></article>"
        for index, item in enumerate(_measurement_plan_rows(), start=1)
    )


def _measurement_plan_rows() -> list[str]:
    return [
        "Test embeddings vs surrogate models",
        "validate on bigger tools to score the time savings",
        "Explore if it's worth to explore combining more than 2 objectives--are these workflows common?",
    ]


def _gap_definitions(
    summary: dict[str, Any], checkpoints: dict[str, Any]
) -> list[tuple[str, str, str, str]]:
    return [
        (
            "No eval-grade model trace",
            (
                f'{checkpoints["trace_rows"]} operational checkpoint rows are supplied, but raw '
                "parent outputs, per-objective latency, cost, and routing decisions are absent."
            ),
            "Persist one versioned record per proposal for both the parent and surrogate paths.",
            "blocks training",
        ),
        (
            "No positive routing holdout",
            (
                f'{summary["negative_challenges"]} hand-crafted negative/OOD challenges exist; '
                "high-value positive and positive-but-uncertain cohorts both have zero samples."
            ),
            "Freeze positive acceptance and uncertain-positive deferral cohorts before tuning gates.",
            "blocks safety claim",
        ),
        (
            "No learned fusion is deployed",
            (
                f'{summary["experimental_surrogates"]} analysis pilot jointly predicts '
                f'{summary["joint_objectives"]} objectives; {summary["registered_surrogates"]} '
                "reviewed FusionBundles are registered."
            ),
            "Train, calibrate, package, and exercise at least one selective joint surrogate.",
            "blocks product claim",
        ),
        (
            "No paired GPU comparison",
            (
                f'{summary["full_model_baselines"]} full-model Modal baselines exist and '
                f'{summary["paired_gpu_comparisons"]} have a paired fused run.'
            ),
            "Run full and fused paths on identical inputs, seeds, stopping rules, and hardware.",
            "blocks speed claim",
        ),
        (
            "Paper-objective parity is incomplete",
            (
                f'{summary["paper_source_count"]} / {summary["fixture_count"]} methodologies '
                "point to paper-specific text; baseline error versus paper scores is not computed."
            ),
            "Version each objective and validate it against the paper or reference implementation.",
            "blocks scientific claim",
        ),
        (
            "Generalization is untested",
            "The only surrogate pilot covers one DNA workload and two algebraically simple outputs.",
            "Add protein and structure workloads plus unseen target/family/scaffold stress tests.",
            "blocks scope claim",
        ),
    ]


def _chunk(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [items[index : index + size] for index in range(0, len(items), size)]


def _slide_heading(index: str, title: str, subtitle: str = "") -> str:
    subtitle_html = (
        f'<p class="heading-note">{_escape(subtitle)}</p>' if subtitle else ""
    )
    return (
        '<header class="heading">'
        f'<div><span class="index">{_escape(index)}</span><h2>{_escape(title)}</h2></div>'
        f"{subtitle_html}</header>"
    )


def _wrap_slides(slides: list[str]) -> str:
    total = len(slides)
    rendered: list[str] = []
    for number, body in enumerate(slides, start=1):
        rendered.append(
            f'<section class="slide" id="slide-{number:02d}">'
            f'<div class="slide-inner">{body}'
            f'<footer class="slide-footer">PROTOFUSE / EVALUATION · {number:02d} / {total:02d}'
            f"</footer></div></section>"
        )
    return "".join(rendered)


def _render_slide_benchmark_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<div class="empty">No benchmark summaries were supplied.</div>'
    head = (
        '<div class="benchmark-table">'
        '<div class="benchmark-head">'
        "<span>Workload</span><span>Work</span><span>Full</span>"
        "<span>Fused</span><span>Objective error</span></div>"
    )
    body = []
    for row in rows:
        fused = row.get("fused_seconds")
        body.append(
            '<div class="benchmark-row">'
            f'<span class="workload"><strong>{_escape(row["workload"])}</strong>'
            f'<small>{_escape(row["tier"])}</small></span>'
            f'<span>{_escape(row["work"])}</span>'
            f'<span class="mono">{_escape(_format_time(row.get("full_seconds")))}</span>'
            f'<span class="mono {"good" if fused is not None else "muted"}">'
            f'{_escape(_format_time(fused))}</span>'
            f'<span>{_escape(row["objective_error"])}</span>'
            "</div>"
        )
    return head + "".join(body) + "</div>"


def _render_slide_paper_study_rows(rows: list[dict[str, str]]) -> str:
    if not rows:
        return '<div class="empty">No methodology fixtures were supplied.</div>'
    head = (
        '<div class="studies-table">'
        '<div class="studies-head">'
        "<span>Workload</span><span>Paper / DOI</span></div>"
    )
    body = []
    for row in rows:
        body.append(
            '<div class="studies-row">'
            f'<span class="workload"><strong>{_escape(row["workload"])}</strong></span>'
            f'<span class="paper-cell"><strong>{_escape(row["paper_title"])}</strong>'
            f'<small class="mono">{_escape(row["identifier"])}</small></span>'
            "</div>"
        )
    return head + "".join(body) + "</div>"


def _render_slide_plan_rows(rows: list[tuple[str, str, str]], start_index: int) -> str:
    return "".join(
        '<article class="plan-row">'
        f'<span class="plan-index">{start_index + offset:02d}</span><div>'
        f"<strong>{_escape(stage)}</strong>"
        f"<h3>{_escape(question)}</h3><p>{_escape(measures)}</p></div></article>"
        for offset, (stage, question, measures) in enumerate(rows)
    )


def _render_slide_surrogate_static(pilot: dict[str, Any]) -> str:
    audit = pilot.get("audit", {})
    support = pilot.get("support", {})
    challenges = support.get("challenge_accepted", {}) if isinstance(support, dict) else {}
    if not isinstance(challenges, dict):
        challenges = {}
    rejected = sum(not bool(value) for value in challenges.values())
    challenge_count = len(challenges)
    audit_cards = "".join(
        (
            _surrogate_metric_card(
                _format_error(audit.get("tissue_mae")),
                "tissue-score MAE",
                "Held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_error(audit.get("gc_percentage_point_mae"), " pp"),
                "GC MAE",
                "Percentage-point error on the held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_percent(support.get("audit_coverage")),
                "audit coverage",
                "Fraction of in-domain audit samples accepted by the support gate.",
            ),
            _surrogate_metric_card(
                f"{rejected} / {challenge_count}",
                "negative challenges rejected",
                "Useful specificity evidence, but the sample is small and hand-crafted.",
            ),
        )
    )
    return (
        '<div class="surrogate-header"><div><span class="kicker">MODEL CARD · CUSTOM eGFP LUNG</span>'
        "<h3>Surrogate performance, with missing metrics made explicit.</h3></div>"
        f'<p>{pilot.get("teacher_samples", 0):,} teacher labels · '
        f'{_format_time(pilot.get("teacher_collection_seconds"))} collection · '
        f'{pilot.get("objective_count", 0)} joint objectives</p></div>'
        f'<div class="surrogate-grid">{audit_cards}</div>'
        '<p class="metric-note"><strong>Metric interpretation:</strong> MAE and maximum error are '
        "appropriate for these continuous outputs. Routing accuracy needs positive holdouts.</p>"
    )


def _render_slide_visualization_condensed(visualizations: dict[str, Any]) -> str:
    candidates = visualizations.get("candidates", [])
    structures = visualizations.get("structures", [])
    molecules = visualizations.get("molecules", [])
    gaps = visualizations.get("gaps", [])
    if not isinstance(candidates, list) or not candidates:
        return '<div class="empty">No curated visualization bundle is available.</div>'
    summary = (
        '<div class="artifact-summary">'
        f'<div><strong>{len(candidates)}</strong><span>sequence artifacts</span></div>'
        f'<div><strong>{len(structures) if isinstance(structures, list) else 0}</strong>'
        "<span>structure artifacts</span></div>"
        f'<div><strong>{len(molecules) if isinstance(molecules, list) else 0}</strong>'
        "<span>molecule artifacts</span></div></div>"
    )
    cards: list[str] = []
    for candidate in candidates[:2]:
        if not isinstance(candidate, dict):
            continue
        sequence = candidate.get("sequence", {})
        if not isinstance(sequence, dict):
            continue
        value = sequence.get("value")
        sequence_type = str(sequence.get("type", "unknown"))
        if not isinstance(value, str) or not value:
            continue
        preview = _escape(value[:48] + ("…" if len(value) > 48 else ""))
        cards.append(
            '<article class="artifact-card"><div class="artifact-head"><div>'
            f'<span class="kicker">{_escape(candidate.get("fixture", "unknown"))} · '
            f'{_escape(candidate.get("tier", "unknown"))}</span>'
            f'<h3>{_escape(candidate.get("segment_label", "construct"))}</h3></div></div>'
            f'<div class="artifact-meta"><span>{_escape(sequence_type)}</span>'
            f"<span>{len(value):,} residues / bases</span></div>"
            f'<p class="mono">{preview}</p></article>'
        )
    gap_count = len(gaps) if isinstance(gaps, list) else 0
    gap_note = (
        f'<p class="artifact-gaps-inline">{gap_count} documented visualization gap(s) remain.</p>'
        if gap_count
        else ""
    )
    return (
        '<div class="artifact-intro"><div><span class="kicker">CURATED VISUALIZATION BUNDLE</span>'
        "<h3>Saved design outputs, not screenshots.</h3></div>"
        "<p>Sequences are embedded for direct inspection in the full report.</p></div>"
        f"{summary}<div class=\"artifact-grid\">{''.join(cards)}</div>{gap_note}"
    )


def _render_slide_appendix(
    summary: dict[str, Any],
    checkpoints: dict[str, Any],
    splits: dict[str, Any],
    source_count: int,
) -> str:
    checkpoint_available = checkpoints["run_count"] > 0
    stats = [
        (
            str(checkpoints["run_count"]),
            "checkpoint runs",
            "Operational resume manifests supplied.",
        ),
        (
            f'{checkpoints["completed_units"]} / {checkpoints["planned_units"]}',
            "completed units",
            "Across supplied checkpoint programs.",
        ),
        (
            str(checkpoints["trace_rows"]),
            "trace rows",
            "Checkpoint trace lines, not eval-grade teacher outputs.",
        ),
        (
            str(source_count),
            "hashed sources",
            "Aggregate inputs recorded in the full report appendix.",
        ),
        (
            f'{summary["paper_source_count"]} / {summary["fixture_count"]}',
            "paper-linked fixtures",
            "Methodology files pointing to paper-specific text.",
        ),
        (
            f'{splits["train"] + splits["calibration"] + splits["audit"]:,}',
            "pilot split rows",
            "Train, calibration, and audit trajectory groups.",
        ),
    ]
    cards = "".join(
        '<article class="metric">'
        f'<div class="metric-value">{_escape(value)}</div>'
        f'<div class="metric-label">{_escape(label)}</div>'
        f"<p>{_escape(detail)}</p></article>"
        for value, label, detail in stats
    )
    trace_state = (
        _state(f'{checkpoints["run_count"]} run(s)', "available")
        if checkpoint_available
        else _state("no manifests supplied", "partial")
    )
    return (
        f"{cards}"
        '<div class="appendix-note">'
        f"<strong>Trace readiness:</strong> run summaries partial · checkpoints {trace_state} · "
        "eval-grade teacher outputs missing · surrogate routing missing."
        "</div>"
    )


def _render_slide_pilot_cards(pilot: dict[str, Any]) -> str:
    chains = pilot.get("comparison_chains")
    identical = pilot.get("identical_final_sequences")
    sequence_result = (
        f"{identical} / {chains}"
        if isinstance(chains, int) and isinstance(identical, int)
        else "not available"
    )
    results = [
        (
            _format_speedup(pilot.get("scoring_speedup")),
            "parent-scoring speedup",
            "Feature extraction plus two-output prediction versus the two CPU objectives.",
        ),
        (
            _format_speedup(pilot.get("end_to_end_speedup")),
            "end-to-end speedup",
            "Observed across the injected 20-chain full pilot; orchestration limits the gain.",
        ),
        (
            sequence_result,
            "identical final sequences",
            "This checks the narrow pilot outcome, not generalization to new objectives or models.",
        ),
        (
            _format_error(pilot.get("max_final_energy_difference")),
            "maximum final-energy difference",
            "The joint linear surrogate is effectively exact for these two simple objectives.",
        ),
    ]
    cards = "".join(
        '<article class="result-card">'
        f'<strong>{_escape(value)}</strong><span>{_escape(label)}</span><p>{_escape(detail)}</p>'
        "</article>"
        for value, label, detail in results
    )
    return (
        '<div class="result-intro"><div><span class="kicker">WHAT THE PILOT ESTABLISHES</span>'
        "<h3>A joint surrogate can reproduce two base-composition objectives.</h3></div>"
        "<p>The CUSTOM experiment fits one ordinary least-squares matrix to tissue codon score "
        "and GC fraction. It is a useful instrumentation proof, but neither objective is an "
        "expensive GPU parent model and no FusionBundle is registered.</p></div>"
        f'<div class="result-grid">{cards}</div>'
    )


def _render_slide_pilot_cards_compact(pilot: dict[str, Any]) -> str:
    chains = pilot.get("comparison_chains")
    identical = pilot.get("identical_final_sequences")
    sequence_result = (
        f"{identical} / {chains}"
        if isinstance(chains, int) and isinstance(identical, int)
        else "not available"
    )
    results = [
        (
            _format_speedup(pilot.get("scoring_speedup")),
            "parent-scoring speedup",
            "Feature extraction plus two-output prediction versus the two CPU objectives.",
        ),
        (
            _format_speedup(pilot.get("end_to_end_speedup")),
            "end-to-end speedup",
            "Observed across the injected 20-chain full pilot; orchestration limits the gain.",
        ),
        (
            sequence_result,
            "identical final sequences",
            "Checks the narrow pilot outcome, not generalization to new objectives or models.",
        ),
        (
            _format_error(pilot.get("max_final_energy_difference")),
            "maximum final-energy difference",
            "The joint linear surrogate is effectively exact for these two simple objectives.",
        ),
    ]
    return "".join(
        '<article class="result-card">'
        f'<strong>{_escape(value)}</strong><span>{_escape(label)}</span><p>{_escape(detail)}</p>'
        "</article>"
        for value, label, detail in results
    )


def _render_slide_surrogate_compact(pilot: dict[str, Any]) -> str:
    audit = pilot.get("audit", {})
    support = pilot.get("support", {})
    challenges = support.get("challenge_accepted", {}) if isinstance(support, dict) else {}
    if not isinstance(challenges, dict):
        challenges = {}
    rejected = sum(not bool(value) for value in challenges.values())
    challenge_count = len(challenges)
    return "".join(
        (
            _surrogate_metric_card(
                _format_error(audit.get("tissue_mae")),
                "tissue-score MAE",
                "Held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_error(audit.get("gc_percentage_point_mae"), " pp"),
                "GC MAE",
                "Percentage-point error on the held-out audit split.",
            ),
            _surrogate_metric_card(
                _format_percent(support.get("audit_coverage")),
                "audit coverage",
                "Fraction of in-domain audit samples accepted by the support gate.",
            ),
            _surrogate_metric_card(
                f"{rejected} / {challenge_count}",
                "negative challenges rejected",
                "Useful specificity evidence, but the sample is small and hand-crafted.",
            ),
        )
    )


def _render_slide_visualization_minimal(visualizations: dict[str, Any]) -> str:
    candidates = visualizations.get("candidates", [])
    structures = visualizations.get("structures", [])
    molecules = visualizations.get("molecules", [])
    gaps = visualizations.get("gaps", [])
    if not isinstance(candidates, list) or not candidates:
        return '<div class="empty">No curated visualization bundle is available.</div>'
    gap_count = len(gaps) if isinstance(gaps, list) else 0
    gap_note = (
        f'<p class="artifact-gaps-inline">{gap_count} documented visualization gap(s) remain.</p>'
        if gap_count
        else ""
    )
    return (
        '<div class="artifact-summary">'
        f'<div><strong>{len(candidates)}</strong><span>sequence artifacts</span></div>'
        f'<div><strong>{len(structures) if isinstance(structures, list) else 0}</strong>'
        "<span>structure artifacts</span></div>"
        f'<div><strong>{len(molecules) if isinstance(molecules, list) else 0}</strong>'
        f"<span>molecule artifacts</span></div></div>{gap_note}"
        "<p class=\"viz-note\">Saved design outputs embedded for inspection in the full report.</p>"
    )


def _render_slide_evidence_combined(
    *,
    metrics: str,
    pilot: dict[str, Any],
    visualizations: dict[str, Any],
    benchmark_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    paper_warning = (
        '<p class="paper-warning"><strong>Paper parity is not established.</strong> '
        f'{summary["paper_source_count"]} / {summary["fixture_count"]} methodology fixtures '
        "point to paper-specific text.</p>"
    )
    return (
        '<div class="evidence-slide">'
        '<section class="evidence-block evidence-metrics">'
        '<p class="block-label">Current evidence summary</p>'
        f'<div class="metrics metrics-compact">{metrics}</div></section>'
        '<div class="evidence-columns">'
        '<section class="evidence-block">'
        '<p class="block-label">What the pilot establishes</p>'
        f'<div class="result-grid result-grid-compact">{_render_slide_pilot_cards_compact(pilot)}</div>'
        "</section>"
        '<section class="evidence-block">'
        '<p class="block-label">Surrogate performance</p>'
        f'<div class="surrogate-grid surrogate-grid-compact">{_render_slide_surrogate_compact(pilot)}</div>'
        "</section></div>"
        '<div class="evidence-columns">'
        '<section class="evidence-block evidence-viz">'
        '<p class="block-label">Curated visualization bundle</p>'
        f"{_render_slide_visualization_minimal(visualizations)}"
        "</section>"
        '<section class="evidence-block evidence-benchmarks">'
        '<p class="block-label">Full-model benchmark summaries</p>'
        f'{_render_slide_benchmark_rows(benchmark_rows)}{paper_warning}'
        "</section></div></div>"
    )


def _render_slide_plan_compact(rows: list[str]) -> str:
    return "".join(
        '<article class="plan-row">'
        f'<span class="plan-index">{index:02d}</span><div>'
        f"<h3>{_escape(item)}</h3></div></article>"
        for index, item in enumerate(rows, start=1)
    )


def _render_slide_measure_next(*, plan_rows: list[str]) -> str:
    return (
        '<div class="next-steps-slide">'
        '<section class="next-steps-block next-steps-plan">'
        '<p class="block-label">What to measure next</p>'
        f'<div class="plan plan-compact plan-full">{_render_slide_plan_compact(plan_rows)}</div>'
        "</section></div>"
    )


def render_slides_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    checkpoints = data["checkpoints"]
    splits = data["splits"]
    pilot = data["pilot"]
    benchmarks = data["benchmarks"]
    metrics = "".join(
        [
            _metric(
                _format_speedup(pilot.get("scoring_speedup")),
                "pilot scoring speedup",
                "CPU feature extraction plus two-output regression versus both parent objectives.",
            ),
            _metric(
                _format_speedup(pilot.get("end_to_end_speedup")),
                "pilot end-to-end speedup",
                "Full 20-chain injected comparison, including optimizer overhead.",
            ),
            _metric(
                summary["full_model_baselines"],
                "full-model Modal baselines",
                "Completed full-path summaries available for the other workloads.",
            ),
            _metric(
                summary["registered_surrogates"],
                "registered FusionBundles",
                "The current surrogate remains analysis-only and is not a routed production bundle.",
            ),
        ]
    )
    benchmark_chunks = _chunk(benchmarks, 4) or [[]]
    paper_studies = data.get("paper_studies", [])
    plan_rows = _measurement_plan_rows()

    slides: list[str] = [
        (
            '<div class="title-slide">'
            "<h1>ProtoFuse</h1>"
            '<p class="title-lede">Proto programs repeatedly call sequence and structure models while '
            "searching for better biological designs. ProtoFuse asks whether recurring groups of "
            "objectives can be learned jointly.</p>"
            '<p class="title-authors">Sai Thatigotla and Philip Thomas</p>'
            "</div>"
        ),
        _slide_heading(
            "01",
            "Why ProtoFuse",
            "Joint surrogates reduce repeated parent calls; routing keeps the full models when risk is high.",
        )
        + '<div class="why-routing-slide"><div class="motivation-grid"><article class="motivation">'
        "<b>01 · COST</b><h3>Repeated model calls dominate.</h3>"
        "<p>An optimizer can score thousands of nearby proposals with the same sequence, structure, "
        "and binding models. Reusing learned local behavior could reduce time, accelerator use, and credits.</p>"
        "</article><article class=\"motivation\"><b>02 · JOIN</b>"
        "<h3>Objectives travel together.</h3>"
        "<p>The opportunity is to learn recurring groups—not replace one model at a time—so feature work "
        "and predictions are shared across the same optimization decision.</p></article></div>"
        '<p class="flow-label">Routing concept</p>'
        '<div class="flow" aria-label="ProtoFuse routing concept"><div><span>Original</span>'
        "<strong>Proto optimization program</strong></div><div><span>Detect</span>"
        "<strong>Recurring expensive objective group</strong></div><div><span>Learn</span>"
        "<strong>Joint calibrated surrogate</strong></div><div><span>Gate</span>"
        "<strong>Check support + uncertainty</strong></div><div><span>Route</span>"
        "<strong>Surrogate or full models</strong></div></div></div>",
        '<div class="studies-slide-frame">'
        + _slide_heading(
            "02",
            "Paper-based benchmarking for common paired tool calls",
        )
        + f'<div class="studies-slide">{_render_slide_paper_study_rows(paper_studies)}</div>'
        + "</div>",
    ]

    slides.extend(
        [
        _slide_heading(
            "03",
            "Current evidence",
            "Observed measurements, pilot results, surrogate metrics, curated outputs, and full-model baselines.",
        )
        + _render_slide_evidence_combined(
            metrics=metrics,
            pilot=pilot,
            visualizations=data["visualizations"],
            benchmark_rows=benchmark_chunks[0] if benchmark_chunks else [],
            summary=summary,
        ),
        ]
    )

    for chunk_index, chunk in enumerate(benchmark_chunks[1:], start=2):
        slides.append(
            _slide_heading(
                "03",
                "Full-model benchmark summaries",
                f"Workload timing and objective error ({chunk_index} / {len(benchmark_chunks)}).",
            )
            + _render_slide_benchmark_rows(chunk)
            + (
                '<p class="paper-warning"><strong>Paper parity is not established.</strong> '
                f'{summary["paper_source_count"]} / {summary["fixture_count"]} methodology fixtures '
                "point to paper-specific text.</p>"
                if chunk_index == len(benchmark_chunks)
                else ""
            )
        )

    slides.append(
        _slide_heading(
            "04",
            "What to measure next",
            "Three priorities before the next claim.",
        )
        + _render_slide_measure_next(plan_rows=plan_rows)
    )

    slides.append(
        _slide_heading(
            "05",
            "Evidence appendix summary",
            "Trace readiness, cohorts, checkpoints, and provenance at a glance.",
        )
        + f'<div class="metrics appendix-metrics">{_render_slide_appendix(summary, checkpoints, splits, len(data["sources"]))}</div>'
    )

    embedded = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    return SLIDES_PAGE_TEMPLATE.replace("__AUDIT_DATE__", _escape(data["audit_date"])).replace(
        "__SLIDES__", _wrap_slides(slides)
    ).replace("__EMBEDDED_JSON__", embedded)


SLIDES_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1920">
<meta name="description" content="ProtoFuse evaluation slide deck (16:9 widescreen)">
<title>ProtoFuse / Evaluation Slides</title>
<style>
:root{--ink:#14233d;--blue:#274d7d;--muted:#667184;--paper:#f4f1e9;--card:#fffdf8;--line:#d7d4cb;--orange:#e55d2f;--green:#16806a;--yellow:#9a640c;--red:#b63a32;--soft-orange:#f6ded4;--soft-blue:#e8eef5;--slide-w:1920px;--slide-h:1080px;--slide-px:88px;--slide-py:68px}
*{box-sizing:border-box}body{margin:0;background:#d8d4cb;color:var(--ink);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.deck{display:flex;flex-direction:column;align-items:center;gap:32px;padding:32px 0 64px}a{color:inherit}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.slide{width:var(--slide-w);height:var(--slide-h);aspect-ratio:16/9;overflow:hidden;background:var(--paper);position:relative;box-shadow:0 8px 32px rgba(20,35,61,.12)}.slide-inner{padding:var(--slide-py) var(--slide-px);height:100%;display:flex;flex-direction:column;gap:20px}
.slide-footer{margin-top:auto;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font:700 10px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}
.eyebrow,.kicker{color:var(--orange);font:800 10px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}
.hero-grid{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:48px;align-items:end;flex:1}.hero-grid h1{margin:16px 0 0;font:700 52px/1.02 Georgia,serif;letter-spacing:-.04em}.hero-grid h1 span{color:var(--orange)}.title-slide{flex:1;display:flex;flex-direction:column;justify-content:center;gap:44px;max-width:1180px;padding-top:12px}.title-slide h1{margin:0;font:700 136px/.94 Georgia,serif;letter-spacing:-.05em;color:var(--ink)}.title-lede{margin:0;max-width:1040px;font-size:34px;line-height:1.58;font-weight:500;color:#24324a}.title-authors{margin:0;padding-top:28px;border-top:2px solid var(--line);font:750 22px ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase;color:var(--orange)}.lede{margin:20px 0 0;color:var(--muted);font-size:18px;line-height:1.65;max-width:920px}
.verdict{padding:24px;background:var(--ink);color:white;border-radius:11px 11px 11px 2px;box-shadow:10px 10px 0 var(--soft-orange)}.verdict small{color:#aebad0;font:750 9px ui-monospace,monospace;text-transform:uppercase}.verdict strong{display:block;margin:12px 0;color:#ff875d;font:780 24px ui-monospace,monospace}.verdict p{margin:0;color:#ccd5e3;font-size:13px;line-height:1.55}
.heading{display:flex;align-items:end;justify-content:space-between;gap:24px;padding-bottom:16px;border-bottom:1px solid var(--line)}.heading>div{display:flex;align-items:baseline;gap:12px}.index{color:var(--orange);font:800 10px ui-monospace,monospace}.heading h2{margin:0;font:700 36px Georgia,serif;letter-spacing:-.025em}.heading-note{max-width:520px;margin:0;color:var(--muted);font-size:13px;line-height:1.5;text-align:right}
.motivation-grid{display:grid;grid-template-columns:repeat(3,1fr);border-left:1px solid var(--line);flex:1}.motivation{padding:22px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.motivation b{color:var(--orange);font:800 10px ui-monospace,monospace}.motivation h3{margin:18px 0 8px;font:700 22px/1.15 Georgia,serif}.motivation p{margin:0;color:var(--muted);font-size:13px;line-height:1.6}
.why-routing-slide{display:flex;flex-direction:column;gap:14px;flex:1;min-height:0}.why-routing-slide .motivation-grid{flex:1.15;border-top:1px solid var(--line);grid-template-columns:repeat(2,1fr)}.why-routing-slide .motivation{padding:28px 30px}.why-routing-slide .motivation b{font:800 15px ui-monospace,monospace;letter-spacing:.12em}.why-routing-slide .motivation h3{margin:18px 0 12px;font:700 30px/1.18 Georgia,serif}.why-routing-slide .motivation p{margin:0;font-size:30px;line-height:1.48;color:#24324a}.flow-label{margin:0;color:var(--orange);font:800 9px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase}
.flow{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--ink);background:var(--ink);gap:1px;flex:1}.flow div{min-height:120px;padding:16px;background:var(--paper);display:flex;flex-direction:column;gap:8px;justify-content:center;position:relative}.why-routing-slide .flow{flex:.85}.why-routing-slide .flow div{min-height:88px;padding:12px 14px}.flow div:not(:last-child):after{content:"→";position:absolute;right:-10px;z-index:2;width:18px;height:18px;display:grid;place-items:center;border:1px solid var(--ink);border-radius:50%;background:var(--paper);font-size:11px}.flow span{color:var(--orange);font:800 8px ui-monospace,monospace;text-transform:uppercase}.flow strong{font-size:12px;line-height:1.4}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-top:3px solid var(--ink);flex:1}.appendix-metrics{grid-template-columns:repeat(3,1fr)}.metric{padding:22px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.metric:nth-child(4n){border-right:0}.appendix-metrics .metric:nth-child(3n){border-right:0}.appendix-metrics .metric:nth-child(4n){border-right:1px solid var(--line)}.metric-value{font:760 30px ui-monospace,monospace;letter-spacing:-.05em}.metric-label{margin-top:12px;font-size:10px;font-weight:850;letter-spacing:.08em;text-transform:uppercase}.metric p{margin:8px 0 0;color:var(--muted);font-size:12px;line-height:1.5}
.evidence-slide{display:flex;flex-direction:column;gap:12px;flex:1;min-height:0}.evidence-slide .block-label{margin:0 0 8px;color:var(--orange);font:800 9px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase}.evidence-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px;flex:1;min-height:0}.evidence-block{display:flex;flex-direction:column;min-height:0;border:1px solid var(--line);background:var(--card);padding:12px 14px}.evidence-metrics .metrics-compact{border-top-width:1px}.metrics-compact .metric{padding:12px 14px}.metrics-compact .metric-value{font-size:22px}.metrics-compact .metric-label{margin-top:8px;font-size:8px}.metrics-compact .metric p{font-size:10px;line-height:1.4}.result-grid-compact,.surrogate-grid-compact{display:grid;grid-template-columns:repeat(2,1fr);border:1px solid var(--line);flex:1}.result-grid-compact .result-card,.surrogate-grid-compact .surrogate-metric{padding:12px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:var(--paper)}.result-grid-compact .result-card:nth-child(2n),.surrogate-grid-compact .surrogate-metric:nth-child(2n){border-right:0}.result-grid-compact .result-card:nth-last-child(-n+2),.surrogate-grid-compact .surrogate-metric:nth-last-child(-n+2){border-bottom:0}.result-grid-compact .result-card strong{font-size:20px}.result-grid-compact .result-card span,.surrogate-grid-compact .surrogate-metric span{margin-top:8px;font-size:8px}.result-grid-compact .result-card p,.surrogate-grid-compact .surrogate-metric p{font-size:10px;line-height:1.4}.surrogate-grid-compact .surrogate-metric strong{font-size:14px}.evidence-viz .artifact-summary{border:1px solid var(--line)}.evidence-viz .artifact-summary div{padding:12px}.evidence-viz .artifact-summary strong{font-size:20px}.evidence-viz .viz-note{margin:10px 0 0;color:var(--muted);font-size:10px;line-height:1.45}.evidence-benchmarks .benchmark-table{flex:1;min-height:0}.evidence-benchmarks .benchmark-head{min-height:28px;font-size:8px}.evidence-benchmarks .benchmark-row{min-height:42px;font-size:11px}.evidence-benchmarks .paper-warning{margin-top:10px;padding:10px 12px;font-size:10px;line-height:1.45}
.result-intro,.surrogate-header{display:grid;grid-template-columns:1.1fr 1fr;gap:40px;align-items:end;padding:24px;background:var(--ink);color:white}.result-intro h3,.surrogate-header h3{margin:8px 0 0;font:700 24px/1.2 Georgia,serif}.result-intro p,.surrogate-header p{margin:0;color:#cbd4e3;font-size:12px;line-height:1.6}.result-grid{display:grid;grid-template-columns:repeat(4,1fr);border-left:1px solid var(--line)}.result-card{padding:20px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.result-card strong{display:block;font:760 26px ui-monospace,monospace}.result-card span,.surrogate-metric span{display:block;margin-top:12px;font:800 9px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase}.result-card p,.surrogate-metric p{margin:8px 0 0;color:var(--muted);font-size:11px;line-height:1.55}
.model-card,.visualization-card{border:1px solid var(--ink);flex:1;display:flex;flex-direction:column;overflow:hidden}.surrogate-header{background:var(--blue)}.surrogate-header p{text-align:right}.surrogate-grid{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--line)}.surrogate-metric{padding:18px;background:var(--card);border-right:1px solid var(--line)}.surrogate-metric:last-child{border-right:0}.surrogate-metric strong{display:block;font:720 17px/1.3 ui-monospace,monospace;overflow-wrap:anywhere}.metric-note{margin:0;padding:14px 18px;background:var(--soft-blue);color:var(--blue);font-size:11px;line-height:1.55}
.artifact-intro{display:grid;grid-template-columns:1.1fr 1fr;gap:36px;align-items:end;padding:22px;background:#263b35;color:white}.artifact-intro h3{margin:8px 0 0;font:700 22px Georgia,serif}.artifact-intro p{margin:0;color:#cbd8d2;font-size:12px;line-height:1.55}.artifact-summary{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--line)}.artifact-summary div{padding:16px;background:var(--card);border-right:1px solid var(--line)}.artifact-summary div:last-child{border-right:0}.artifact-summary strong{display:block;font:760 24px ui-monospace,monospace}.artifact-summary span{font:800 8px ui-monospace,monospace;text-transform:uppercase}.artifact-grid{display:grid;grid-template-columns:1fr 1fr;border-left:1px solid var(--line)}.artifact-card{padding:18px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.artifact-head h3{margin:6px 0 0;font:700 18px Georgia,serif}.artifact-meta{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}.artifact-meta span{padding:4px 7px;border-radius:999px;background:#ebe7dd;font:750 8px ui-monospace,monospace;text-transform:uppercase}.artifact-card p{margin:0;color:var(--muted);font-size:11px;line-height:1.5}.artifact-gaps-inline{margin:0;padding:12px 16px;background:#fff8e8;color:var(--yellow);font-size:11px;border-top:1px solid var(--line)}
.paper-warning{margin:0;padding:14px 16px;background:#fff8e8;border:1px solid #e5d4ad;font-size:12px;line-height:1.55}.studies-slide-frame{display:flex;flex-direction:column;flex:1;min-height:0;gap:20px}.studies-slide-frame .heading h2{font-size:30px}.studies-slide{display:flex;flex-direction:column;flex:1;min-height:0}.studies-table{border:1px solid var(--line);flex:1;display:flex;flex-direction:column;overflow:hidden}.studies-head,.studies-row{display:grid;grid-template-columns:1fr 2.35fr;align-items:center;gap:8px;padding:0 10px}.studies-head{min-height:48px;border-bottom:1px solid var(--line);color:var(--muted);font:800 30px ui-monospace,monospace;letter-spacing:.04em;text-transform:uppercase;background:var(--card)}.studies-row{min-height:30px;border-bottom:1px solid var(--line);background:rgba(255,253,248,.85);font-size:10px;line-height:1.25}.studies-row:last-child{border-bottom:0}.studies-row .workload strong{font-size:11px}.paper-cell{display:flex;flex-direction:column;gap:2px}.paper-cell strong{font-size:10px;line-height:1.25;font-weight:650}.paper-cell small{font-size:9px;color:var(--muted);overflow-wrap:anywhere}.benchmark-table{border:1px solid var(--line);flex:1;display:flex;flex-direction:column;overflow:hidden}.benchmark-head,.benchmark-row{display:grid;grid-template-columns:1.35fr 1fr .7fr .7fr 1.5fr;align-items:center;gap:12px;padding:0 12px}.benchmark-head{min-height:36px;border-bottom:1px solid var(--line);color:var(--muted);font:800 9px ui-monospace,monospace;text-transform:uppercase;background:var(--card)}.benchmark-row{min-height:56px;border-bottom:1px solid var(--line);background:rgba(255,253,248,.85);font-size:12px}.benchmark-row:last-child{border-bottom:0}.workload{display:flex;flex-direction:column;gap:4px}.workload strong{font-size:13px}.workload small{color:var(--muted);font:650 9px ui-monospace,monospace;text-transform:uppercase}.good{color:var(--green);font-weight:800}.muted{color:var(--muted)}.empty{padding:28px;background:var(--card);color:var(--muted);text-align:center}
.gap-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;flex:1}.gap-card{padding:20px;background:var(--card);border:1px solid var(--line);border-top:3px solid var(--orange)}.gap-meta{display:flex;justify-content:space-between;align-items:center;color:var(--orange);font:800 9px ui-monospace,monospace;text-transform:uppercase}.gap-meta b{padding:4px 7px;border-radius:999px;background:var(--soft-orange);color:var(--red)}.gap-card h3{margin:16px 0 10px;font:700 20px Georgia,serif}.gap-card p{margin:6px 0;color:var(--muted);font-size:11px;line-height:1.55}.gap-card p strong{color:var(--ink)}
.next-steps-slide{display:flex;flex-direction:column;flex:1;min-height:0}.next-steps-block{display:flex;flex-direction:column;min-height:0;border:1px solid var(--line);background:var(--card);padding:12px 14px}.next-steps-plan{flex:1}.next-steps-block .block-label{margin:0 0 8px;color:var(--orange);font:800 9px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase}.plan-compact{border-left:1px solid var(--line);flex:1;overflow:hidden;display:flex;flex-direction:column}.plan-compact.plan-full .plan-row{flex:1;grid-template-columns:64px 1fr}.plan-compact .plan-row{grid-template-columns:42px 1fr}.plan-compact .plan-index{font-size:10px}.plan-compact.plan-full .plan-index{font-size:18px}.plan-compact .plan-row>div{padding:10px 12px}.plan-compact.plan-full .plan-row>div{display:flex;align-items:center;padding:28px 32px}.plan-compact .plan-row h3{margin:4px 0 2px;font-size:13px;line-height:1.2}.plan-compact.plan-full .plan-row h3{margin:0;font-size:34px;line-height:1.25}.plan-compact .plan-row p{font-size:9px;line-height:1.4}
.plan{border-left:1px solid var(--line);flex:1}.plan-row{display:grid;grid-template-columns:64px 1fr;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.plan-index{display:grid;place-items:center;color:var(--orange);background:#ebe7dd;font:800 12px ui-monospace,monospace}.plan-row>div{padding:18px 22px}.plan-row>div>strong{color:var(--orange);font:800 9px ui-monospace,monospace;text-transform:uppercase}.plan-row h3{margin:6px 0 4px;font:700 18px Georgia,serif}.plan-row p{margin:0;color:var(--muted);font-size:11px;line-height:1.55}
.appendix-note{margin-top:8px;padding:14px 16px;background:var(--soft-blue);color:var(--blue);font-size:12px;line-height:1.55;border:1px solid var(--line)}.state{white-space:nowrap;border-radius:999px;padding:4px 8px;font:800 8px ui-monospace,monospace;text-transform:uppercase}.state.available{color:var(--green);background:#dceee8}.state.partial{color:var(--yellow);background:#f5e7c8}.state.missing{color:var(--red);background:#f4dcd8}
@media print{@page{size:10in 5.625in;margin:0}html,body{margin:0;padding:0;background:var(--paper);-webkit-print-color-adjust:exact;print-color-adjust:exact}.deck{display:block;gap:0;padding:0}.slide{display:block;width:10in;height:5.625in;max-height:5.625in;aspect-ratio:16/9;box-shadow:none;overflow:hidden;page-break-after:always;break-after:page;page-break-inside:avoid;break-inside:avoid}.slide:last-child{page-break-after:auto;break-after:auto}}
</style>
</head>
<body>
<div class="deck" aria-label="ProtoFuse evaluation slides · audit __AUDIT_DATE__">
__SLIDES__
</div>
<script type="application/json" id="protofuse-report-data">__EMBEDDED_JSON__</script>
</body>
</html>
"""


def render_report(data: dict[str, Any]) -> str:
    summary = data["summary"]
    checkpoints = data["checkpoints"]
    splits = data["splits"]
    pilot = data["pilot"]
    checkpoint_available = checkpoints["run_count"] > 0
    checkpoint_state = (
        _state(f'{checkpoints["run_count"]} run(s)', "available")
        if checkpoint_available
        else _state("no manifests supplied", "partial")
    )
    trace_rows = (
        '<article class="trace"><div><strong>Run summaries</strong><p>Aggregate Modal and '
        f'pilot result files supplied.</p></div>{_state("partial", "partial")}</article>'
        '<article class="trace"><div><strong>Operational checkpoints</strong><p>Atomic '
        'optimizer/RNG state and completion ledgers when checkpoint files are supplied.</p></div>'
        f"{checkpoint_state}</article>"
        '<article class="trace"><div><strong>Eval-grade teacher outputs</strong><p>Raw parent '
        'outputs, objective components, latency, and cost are not in the current aggregates.</p>'
        f'</div>{_state("missing", "missing")}</article>'
        '<article class="trace"><div><strong>Surrogate routing</strong><p>No registered bundle '
        'emits prediction, uncertainty, route, and deferral records.</p>'
        f'</div>{_state("missing", "missing")}</article>'
    )
    cohort_rows = [
        ("Train", splits["train"], "CUSTOM trajectory groups 0–2", "available"),
        ("Calibration / val", splits["calibration"], "CUSTOM trajectory group 3", "available"),
        ("Audit / test", splits["audit"], "CUSTOM trajectory group 4", "available"),
        (
            "Full-trajectory holdout",
            splits["full_trajectory"],
            "Separate held-out trajectories",
            "available",
        ),
        ("Negative / OOD", splits["negative_ood"], "Hand-crafted challenges", "partial"),
        ("High-value positives", splits["positive"], "No positive acceptance set", "missing"),
        (
            "Positive but uncertain",
            splits["positive_uncertain"],
            "No safe-deferral set",
            "missing",
        ),
    ]
    cohorts = "".join(
        '<div class="cohort">'
        f"<strong>{_escape(name)}</strong><span class=\"mono\">{count:,}</span>"
        f"<span>{_escape(coverage)}</span>{_state(verdict, verdict)}</div>"
        for name, count, coverage, verdict in cohort_rows
    )
    source_rows = "".join(
        '<tr><td class="mono">'
        f'{_escape(source["path"])}</td><td class="mono hash">{_escape(source["sha256"])}</td></tr>'
        for source in data["sources"]
    ) or '<tr><td colspan="2">No source artifacts supplied.</td></tr>'
    embedded = json.dumps(data, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    metrics = "".join(
        [
            _metric(
                _format_speedup(pilot.get("scoring_speedup")),
                "pilot scoring speedup",
                "CPU feature extraction plus two-output regression versus both parent objectives.",
            ),
            _metric(
                _format_speedup(pilot.get("end_to_end_speedup")),
                "pilot end-to-end speedup",
                "Full 20-chain injected comparison, including optimizer overhead.",
            ),
            _metric(
                summary["full_model_baselines"],
                "full-model Modal baselines",
                "Completed full-path summaries available for the other workloads.",
            ),
            _metric(
                summary["registered_surrogates"],
                "registered FusionBundles",
                "The current surrogate remains analysis-only and is not a routed production bundle.",
            ),
        ]
    )
    benchmark_html = _render_benchmarks(data["benchmarks"])
    pilot_html = _render_pilot(pilot)
    surrogate_metrics_html = _render_surrogate_metrics(pilot)
    visualization_html = _render_visualization_assets(data["visualizations"])
    gaps_html = _render_gaps(summary, checkpoints)
    measurement_plan = _render_measurement_plan()
    return PAGE_TEMPLATE.replace("__AUDIT_DATE__", _escape(data["audit_date"])).replace(
        "__GENERATED_AT__", _escape(data["generated_at"])
    ).replace("__METRICS__", metrics).replace("__PILOT_RESULTS__", pilot_html).replace(
        "__SURROGATE_METRICS__", surrogate_metrics_html
    ).replace(
        "__VISUALIZATION_ASSETS__", visualization_html
    ).replace(
        "__GAP_CARDS__", gaps_html
    ).replace("__MEASUREMENT_PLAN__", measurement_plan).replace(
        "__CHECKPOINT_RUNS__", _escape(checkpoints["run_count"])
    ).replace(
        "__CHECKPOINT_RESUMES__", _escape(checkpoints["resume_count"])
    ).replace(
        "__CHECKPOINT_UNITS__",
        _escape(f'{checkpoints["completed_units"]} / {checkpoints["planned_units"]}'),
    ).replace(
        "__CHECKPOINT_TRACE_ROWS__", _escape(checkpoints["trace_rows"])
    ).replace("__TRACE_ROWS__", trace_rows).replace(
        "__COHORT_ROWS__", cohorts
    ).replace("__BENCHMARK_ROWS__", benchmark_html).replace(
        "__PAPER_SOURCES__",
        _escape(f'{summary["paper_source_count"]} / {summary["fixture_count"]}'),
    ).replace("__SOURCE_ROWS__", source_rows).replace(
        "__EMBEDDED_JSON__", embedded
    )


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Portable interactive ProtoFuse evaluation report">
<title>ProtoFuse / Motivation, Results & Gaps</title>
<style>
:root{--ink:#14233d;--blue:#274d7d;--muted:#667184;--paper:#f4f1e9;--card:#fffdf8;--line:#d7d4cb;--orange:#e55d2f;--green:#16806a;--yellow:#9a640c;--red:#b63a32;--soft-orange:#f6ded4;--soft-blue:#e8eef5}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:inherit}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.topbar{min-height:62px;padding:0 max(22px,5vw);display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line);background:rgba(244,241,233,.96);backdrop-filter:blur(9px);position:sticky;top:0;z-index:4}.brand{font-size:12px;font-weight:850;letter-spacing:.14em}.brand b{color:var(--orange)}.topbar nav{display:flex;gap:22px}.topbar nav a{color:var(--muted);font:750 9px ui-monospace,monospace;letter-spacing:.05em;text-decoration:none;text-transform:uppercase}.topbar nav a:hover{color:var(--orange)}.portable{display:flex;align-items:center;gap:8px;color:var(--green);font:750 9px ui-monospace,monospace;text-transform:uppercase}.portable:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--green)}
.hero{padding:88px max(24px,7vw) 76px;border-bottom:1px solid var(--line);background:radial-gradient(circle at 89% 10%,rgba(39,77,125,.12),transparent 30%),linear-gradient(180deg,#fbf8f1,var(--paper))}.hero-grid{max-width:1180px;margin:auto;display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:72px;align-items:end}.eyebrow,.kicker{color:var(--orange);font:800 10px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}.hero h1{max-width:840px;margin:18px 0 0;font:700 clamp(45px,6.4vw,82px)/.99 Georgia,serif;letter-spacing:-.047em}.hero h1 span{color:var(--orange)}.lede{max-width:790px;margin:26px 0 0;color:var(--muted);font-size:16px;line-height:1.7}.verdict{padding:25px;background:var(--ink);color:white;border-radius:11px 11px 11px 2px;box-shadow:11px 11px 0 var(--soft-orange)}.verdict small{color:#aebad0;font:750 9px ui-monospace,monospace;text-transform:uppercase}.verdict strong{display:block;margin:13px 0;color:#ff875d;font:780 25px ui-monospace,monospace}.verdict p{margin:0;color:#ccd5e3;font-size:12px;line-height:1.6}
.shell{max-width:1180px;margin:auto;padding:82px 0 0}.heading{display:flex;align-items:end;justify-content:space-between;gap:25px;padding-bottom:18px;border-bottom:1px solid var(--ink)}.heading>div{display:flex;align-items:baseline;gap:14px}.index{color:var(--orange);font:800 10px ui-monospace,monospace}.heading h2{margin:0;font:700 32px Georgia,serif;letter-spacing:-.025em}.heading p{max-width:430px;margin:0 0 3px;color:var(--muted);font-size:12px;line-height:1.5;text-align:right}
.motivation-grid{display:grid;grid-template-columns:repeat(3,1fr);border-left:1px solid var(--line)}.motivation{min-height:230px;padding:27px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.motivation b{color:var(--orange);font:800 10px ui-monospace,monospace}.motivation h3{margin:24px 0 10px;font:700 22px/1.15 Georgia,serif}.motivation p{margin:0;color:var(--muted);font-size:12px;line-height:1.65}.flow{margin-top:24px;display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--ink);background:var(--ink);gap:1px}.flow div{min-height:100px;padding:17px;background:var(--paper);display:flex;flex-direction:column;gap:8px;justify-content:center;position:relative}.flow div:not(:last-child):after{content:"→";position:absolute;right:-10px;z-index:2;width:19px;height:19px;display:grid;place-items:center;border:1px solid var(--ink);border-radius:50%;background:var(--paper);font-size:11px}.flow span{color:var(--orange);font:800 8px ui-monospace,monospace;text-transform:uppercase}.flow strong{font-size:11px;line-height:1.4}
.metrics{max-width:1180px;margin:28px auto 0;display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-top:3px solid var(--ink)}.metric{min-height:160px;padding:24px;background:var(--card);border-right:1px solid var(--line)}.metric:last-child{border-right:0}.metric-value{font:760 33px ui-monospace,monospace;letter-spacing:-.05em}.metric-label{margin-top:15px;font-size:9px;font-weight:850;letter-spacing:.08em;text-transform:uppercase}.metric p{margin:9px 0 0;color:var(--muted);font-size:11px;line-height:1.5}
.result-intro,.surrogate-header{display:grid;grid-template-columns:1.1fr 1fr;gap:60px;align-items:end;padding:30px;background:var(--ink);color:white}.result-intro h3,.surrogate-header h3{margin:10px 0 0;font:700 25px/1.2 Georgia,serif}.result-intro p,.surrogate-header p{margin:0;color:#cbd4e3;font-size:12px;line-height:1.65}.result-grid{display:grid;grid-template-columns:repeat(4,1fr);border-left:1px solid var(--line)}.result-card{min-height:175px;padding:22px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.result-card strong{display:block;font:760 27px ui-monospace,monospace}.result-card span,.surrogate-metric span{display:block;margin-top:14px;font:800 9px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase}.result-card p,.surrogate-metric p{margin:9px 0 0;color:var(--muted);font-size:11px;line-height:1.55}
.model-card{margin-top:28px;border:1px solid var(--ink)}.surrogate-header{background:var(--blue)}.surrogate-header p{text-align:right}.surrogate-model-grid,.surrogate-grid{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--line)}.surrogate-metric{min-height:142px;padding:20px;background:var(--card);border-right:1px solid var(--line)}.surrogate-metric:last-child{border-right:0}.surrogate-metric strong{display:block;font:720 18px/1.3 ui-monospace,monospace;overflow-wrap:anywhere}.tab-list{display:flex;gap:5px;padding:12px;background:#ebe7dd;border-bottom:1px solid var(--line)}.tab{padding:9px 13px;border:1px solid transparent;border-radius:999px;background:transparent;color:var(--muted);font:800 9px ui-monospace,monospace;text-transform:uppercase;cursor:pointer}.tab:hover{border-color:var(--line);color:var(--ink)}.tab.active{background:var(--ink);color:white}.tab-panel{display:none}.tab-panel.active{display:block}.challenge-table{width:100%;border-collapse:collapse;background:var(--card);font-size:11px}.challenge-table th,.challenge-table td{padding:11px 16px;text-align:left;border-top:1px solid var(--line)}.challenge-table th{color:var(--muted);font:800 8px ui-monospace,monospace;text-transform:uppercase}.metric-note{margin:0;padding:16px 20px;background:var(--soft-blue);color:var(--blue);font-size:11px;line-height:1.6}
.visualization-card{margin-top:28px;border:1px solid var(--ink)}.artifact-intro{display:grid;grid-template-columns:1.1fr 1fr;gap:50px;align-items:end;padding:28px;background:#263b35;color:white}.artifact-intro h3{margin:9px 0 0;font:700 24px Georgia,serif}.artifact-intro p{margin:0;color:#cbd8d2;font-size:12px;line-height:1.6}.artifact-summary{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--line)}.artifact-summary div{padding:18px;background:var(--card);border-right:1px solid var(--line)}.artifact-summary div:last-child{border:0}.artifact-summary strong{display:block;font:760 25px ui-monospace,monospace}.artifact-summary span{font:800 8px ui-monospace,monospace;text-transform:uppercase}.artifact-grid{display:grid;grid-template-columns:1fr 1fr}.artifact-card{padding:22px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.artifact-head{display:flex;justify-content:space-between;gap:16px}.artifact-head h3{margin:8px 0 0;font:700 19px Georgia,serif}.artifact-meta{display:flex;flex-wrap:wrap;gap:7px;margin:16px 0}.artifact-meta span{padding:5px 7px;border-radius:999px;background:#ebe7dd;font:750 8px ui-monospace,monospace;text-transform:uppercase}.sequence-view{border:1px solid var(--line);background:#f1eee6}.sequence-view summary{padding:10px;cursor:pointer;font:800 8px ui-monospace,monospace;text-transform:uppercase}.sequence-track{padding:12px;background:#fff;line-height:1.55;overflow-wrap:anywhere}.residue{display:inline-block;min-width:.66em;text-align:center}.residue-hydrophobic{color:#805f16}.residue-positive{color:#245da8}.residue-negative{color:#bf453a}.residue-polar{color:#1e7d67}.residue-special{color:#8b4b9f}.base-a{color:#16806a}.base-c{color:#245da8}.base-g{color:#d17a16}.base-t{color:#b63a32}.artifact-card p{margin:12px 0 0;color:var(--muted);font-size:10px;line-height:1.5}.artifact-card a{color:var(--blue);font-weight:750}.artifact-gaps{padding:18px 22px;background:#fff8e8;color:var(--yellow);font-size:11px;line-height:1.55}.artifact-gaps ul{margin:8px 0 0;padding-left:18px}
.paper-warning,.callout{margin:20px 0;padding:16px 18px;background:#fff8e8;border:1px solid #e5d4ad;font-size:12px;line-height:1.6}.benchmark-head,.benchmark summary{display:grid;grid-template-columns:1.35fr 1fr .7fr .7fr 1.5fr;align-items:center;gap:16px}.benchmark-head{min-height:40px;border-bottom:1px solid var(--line);color:var(--muted);font:800 9px ui-monospace,monospace;text-transform:uppercase}.benchmark{border-bottom:1px solid var(--line)}.benchmark summary{min-height:78px;padding:0 10px;background:rgba(255,253,248,.75);cursor:pointer;font-size:11px}.benchmark summary:hover{background:var(--card)}.workload{display:flex;flex-direction:column;gap:5px}.workload strong{font-size:13px}.workload small{color:var(--muted);font:650 9px ui-monospace,monospace;text-transform:uppercase}.good{color:var(--green);font-weight:800}.muted{color:var(--muted)}.benchmark-detail{display:grid;grid-template-columns:1fr .7fr 2fr;gap:24px;padding:18px 20px;background:#ebe8df}.benchmark-detail div{display:flex;flex-direction:column;gap:6px}.benchmark-detail span{color:var(--muted);font:800 8px ui-monospace,monospace;text-transform:uppercase}.benchmark-detail strong{font-size:11px;line-height:1.5}.empty{padding:35px;background:var(--card);color:var(--muted);text-align:center}
.gap-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:22px}.gap-card{min-height:238px;padding:25px;background:var(--card);border:1px solid var(--line);border-top:3px solid var(--orange)}.gap-meta{display:flex;justify-content:space-between;align-items:center;color:var(--orange);font:800 9px ui-monospace,monospace;text-transform:uppercase}.gap-meta b{padding:5px 7px;border-radius:999px;background:var(--soft-orange);color:var(--red)}.gap-card h3{margin:24px 0 15px;font:700 22px Georgia,serif}.gap-card p{margin:8px 0;color:var(--muted);font-size:11px;line-height:1.55}.gap-card p strong{color:var(--ink)}
.plan{border-left:1px solid var(--line)}.plan-row{display:grid;grid-template-columns:70px 1fr;min-height:140px;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.plan-index{display:grid;place-items:center;color:var(--orange);background:#ebe7dd;font:800 13px ui-monospace,monospace}.plan-row>div{padding:22px 28px}.plan-row>div>strong{color:var(--orange);font:800 9px ui-monospace,monospace;text-transform:uppercase}.plan-row h3{margin:8px 0 6px;font:700 19px Georgia,serif}.plan-row p{margin:0;color:var(--muted);font-size:11px;line-height:1.55}
	.appendix{margin-top:20px;border:1px solid var(--line);background:var(--card)}.appendix>summary{padding:22px;cursor:pointer;font:800 10px ui-monospace,monospace;text-transform:uppercase}.appendix-body{padding:0 22px 22px}.appendix h3{margin:30px 0 12px;font:700 21px Georgia,serif}.trace-grid{display:grid;grid-template-columns:1fr 1fr;border-left:1px solid var(--line)}.trace{min-height:112px;padding:22px;display:flex;justify-content:space-between;gap:16px;background:rgba(255,253,248,.7);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}.trace strong{font-size:13px}.trace p{margin:7px 0 0;color:var(--muted);font-size:12px;line-height:1.5}.state{align-self:flex-start;white-space:nowrap;border-radius:999px;padding:5px 8px;font:800 8px ui-monospace,monospace;text-transform:uppercase}.state.available{color:var(--green);background:#dceee8}.state.partial{color:var(--yellow);background:#f5e7c8}.state.missing{color:var(--red);background:#f4dcd8}.cohorts{border-top:1px solid var(--line);border-left:1px solid var(--line)}.cohort{min-height:58px;display:grid;grid-template-columns:1.15fr 90px 2fr 100px;align-items:center;background:var(--card);border-right:1px solid var(--line);border-bottom:1px solid var(--line);font-size:11px}.cohort>*{margin:0 13px}.checkpoint{display:grid;grid-template-columns:1.4fr repeat(4,1fr);color:white;background:var(--ink);border-radius:8px;overflow:hidden}.checkpoint>div{min-height:82px;padding:16px;display:flex;flex-direction:column;justify-content:center;gap:7px;border-right:1px solid #314363}.checkpoint>div:last-child{border:0}.checkpoint .checkpoint-title{background:#213451}.checkpoint span{color:#aebad0;font:800 8px ui-monospace,monospace;text-transform:uppercase}.checkpoint strong{font-size:11px}.checkpoint-title strong{font:700 16px Georgia,serif}.source-wrap{overflow-x:auto}.sources{width:100%;border-collapse:collapse;background:var(--card);font-size:10px}.sources th,.sources td{padding:11px 13px;text-align:left;border:1px solid var(--line)}.sources th{background:#e9e5dc;text-transform:uppercase;letter-spacing:.08em}.hash{word-break:break-all;color:var(--muted)}.use-note{margin-top:22px;padding:18px;background:var(--soft-blue);color:var(--blue);font-size:11px;line-height:1.65}.use-note code{font:650 10px ui-monospace,monospace}.footer{max-width:1180px;margin:72px auto 0;padding:22px 0 36px;display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--ink);color:var(--muted);font:700 9px ui-monospace,monospace;text-transform:uppercase}
	.trajectory-guide{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--line);background:var(--card)}.trajectory-guide article{min-height:145px;padding:20px;border-right:1px solid var(--line)}.trajectory-guide article:last-child{border-right:0}.trajectory-guide b{color:var(--orange);font:800 9px ui-monospace,monospace;text-transform:uppercase}.trajectory-guide strong{display:block;margin-top:15px;font:700 17px Georgia,serif}.trajectory-guide p{margin:9px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.trajectory-target{padding:16px 18px;color:white;background:var(--blue);font-size:11px;line-height:1.6}.trajectory-target strong{font-size:12px}
@media(max-width:1000px){.hero-grid{grid-template-columns:1fr}.verdict{max-width:440px}.motivation-grid{grid-template-columns:1fr 1fr}.flow{grid-template-columns:1fr 1fr}.flow div:not(:last-child):after{display:none}.metrics,.result-grid,.surrogate-model-grid,.surrogate-grid{grid-template-columns:1fr 1fr}.metric:nth-child(2),.result-card:nth-child(2),.surrogate-metric:nth-child(2){border-right:0}.shell,.footer,.metrics{margin-left:24px;margin-right:24px}.result-intro,.surrogate-header,.artifact-intro{grid-template-columns:1fr;gap:18px}.surrogate-header p{text-align:left}.checkpoint{grid-template-columns:1fr 1fr}.checkpoint-title{grid-column:1/-1}}
	@media(max-width:680px){.topbar nav{display:none}.hero{padding:58px 20px}.hero h1{font-size:43px}.portable{display:none}.shell,.footer{margin-left:18px;margin-right:18px;padding-top:60px}.heading{align-items:flex-start;flex-direction:column}.heading p{text-align:left}.motivation-grid,.flow,.metrics,.result-grid,.surrogate-model-grid,.surrogate-grid,.artifact-summary,.artifact-grid,.gap-grid,.trace-grid,.checkpoint,.trajectory-guide{grid-template-columns:1fr}.metric,.result-card,.surrogate-metric,.motivation,.artifact-summary div,.artifact-card,.trajectory-guide article{border-right:0;border-bottom:1px solid var(--line)}.metrics{margin-left:0;margin-right:0}.checkpoint-title{grid-column:auto}.tab-list{overflow-x:auto}.cohorts,.benchmark-table{overflow-x:auto}.cohort{min-width:650px}.benchmark-head,.benchmark summary{min-width:850px}.footer{flex-direction:column}}
@media print{.topbar{position:static}.hero{padding-top:40px}.verdict,.checkpoint{print-color-adjust:exact;-webkit-print-color-adjust:exact}.tab-panel{display:block}.tab-list{display:none}.benchmark,.gap-card,.plan-row{break-inside:avoid}.shell{padding-top:44px}}
</style>
</head>
<body>
<header class="topbar"><div class="brand">PROTOFUSE <b>/</b> EVALUATION</div><nav><a href="#why">Why</a><a href="#results">Results</a><a href="#gaps">Gaps</a><a href="#measure">Measure next</a></nav><div class="portable">portable interactive report</div></header>
<section class="hero"><div class="hero-grid"><div><div class="eyebrow">motivation · evidence · next measurements · audit __AUDIT_DATE__</div><h1>Make expensive design loops faster.<br><span>Keep the full models when risk is high.</span></h1><p class="lede">Proto programs repeatedly call sequence and structure models while searching for better biological designs. ProtoFuse asks whether recurring groups of objectives can be learned jointly—then used only where a calibrated gate has evidence to trust them.</p></div><aside class="verdict"><small>Current conclusion</small><strong>PROMISING / UNPROVEN</strong><p>One narrow CPU surrogate is fast and effectively exact. No learned fusion has yet been tested against the expensive GPU parent workloads, paper-matched scores, or positive routing holdouts.</p></aside></div></section>

<section class="shell" id="why"><div class="heading"><div><span class="index">01</span><h2>Why ProtoFuse</h2></div><p>The value is not merely a smaller model. It is fewer repeated parent calls across a joint objective group.</p></div><div class="motivation-grid"><article class="motivation"><b>01 · COST</b><h3>Repeated model calls dominate.</h3><p>An optimizer can score thousands of nearby proposals with the same sequence, structure, and binding models. Reusing learned local behavior could reduce time, accelerator use, and credits.</p></article><article class="motivation"><b>02 · JOIN</b><h3>Objectives travel together.</h3><p>The opportunity is to learn recurring groups—not replace one model at a time—so feature work and predictions are shared across the same optimization decision.</p></article><article class="motivation"><b>03 · TRUST</b><h3>Deferral is part of the design.</h3><p>Unmatched, uncertain, out-of-distribution, or failed cases must retain the original full-model path. Coverage matters only alongside selective risk.</p></article></div><div class="flow" aria-label="ProtoFuse routing concept"><div><span>Original</span><strong>Proto optimization program</strong></div><div><span>Detect</span><strong>Recurring expensive objective group</strong></div><div><span>Learn</span><strong>Joint calibrated surrogate</strong></div><div><span>Gate</span><strong>Check support + uncertainty</strong></div><div><span>Route</span><strong>Surrogate or full models</strong></div></div></section>

<section class="metrics" aria-label="Current evidence summary">__METRICS__</section>

<section class="shell" id="results"><div class="heading"><div><span class="index">02</span><h2>What the current results show</h2></div><p>Observed measurements are separated from the claims they cannot yet support.</p></div>__PILOT_RESULTS__<div class="model-card">__SURROGATE_METRICS__</div><div class="visualization-card">__VISUALIZATION_ASSETS__</div><div class="paper-warning"><strong>Paper parity is not established.</strong> __PAPER_SOURCES__ methodology fixtures point to paper-specific text; current final energies are internal composites unless explicitly objective-matched.</div><div class="benchmark-table"><div class="benchmark-head"><span>Workload</span><span>Work</span><span>Full</span><span>Fused</span><span>Objective error</span></div>__BENCHMARK_ROWS__</div></section>

<section class="shell" id="gaps"><div class="heading"><div><span class="index">03</span><h2>What blocks the next claim</h2></div><p>Each gap names the evidence we have and the measurement that would close it.</p></div><div class="gap-grid">__GAP_CARDS__</div></section>

<section class="shell" id="measure"><div class="heading"><div><span class="index">04</span><h2>What to measure next</h2></div><p>Three priorities before the next claim.</p></div><div class="plan">__MEASUREMENT_PLAN__</div></section>

	<section class="shell" id="evidence"><div class="heading"><div><span class="index">05</span><h2>Evidence appendix</h2></div><p>Trace readiness, cohorts, checkpoints, and hashed aggregate inputs.</p></div><details class="appendix"><summary>Open trace, split, checkpoint & provenance detail</summary><div class="appendix-body"><h3>Trace coverage</h3><div class="trace-grid">__TRACE_ROWS__</div><div class="callout"><strong>Checkpointing is not tracing.</strong> Checkpoints support recovery from completed compute boundaries. Evals additionally need proposal-level teacher, surrogate, routing, latency, cost, and final-validation records.</div><h3>How trajectories become model splits</h3><div class="trajectory-guide"><article><b>01 · run</b><strong>One seed creates one trajectory</strong><p>A complete optimizer run emits many sequential proposals whose later states depend on earlier decisions.</p></article><article><b>02 · group</b><strong>Many rows remain one unit</strong><p>Objective rows align into proposal-level teacher samples, but every sample from the trajectory retains one group ID.</p></article><article><b>03 · split</b><strong>Assign complete trajectories</strong><p>Whole groups go to train, calibration, or test. Shuffling proposal rows would leak neighboring optimizer states.</p></article></div><div class="trajectory-target"><strong>Preferred narrow-workload collection:</strong> 60 train + 20 calibration + 20 untouched test trajectories, followed by roughly 50 fresh paired timing trajectories and 40–60 designed challenge cases. Proposal-row counts are larger, but the trajectory counts are the effective independent sample sizes.</div><h3>Training and held-out cohorts</h3><div class="cohorts">__COHORT_ROWS__</div><h3>Resume evidence</h3><section class="checkpoint" aria-label="Checkpoint artifacts"><div class="checkpoint-title"><span>Supplied checkpoint data</span><strong>Operational checkpoints</strong></div><div><span>Runs</span><strong>__CHECKPOINT_RUNS__</strong></div><div><span>Resume events</span><strong>__CHECKPOINT_RESUMES__</strong></div><div><span>Completed / planned units</span><strong>__CHECKPOINT_UNITS__</strong></div><div><span>Trace rows</span><strong>__CHECKPOINT_TRACE_ROWS__</strong></div></section><h3>Hashed aggregate inputs</h3><div class="source-wrap"><table class="sources"><thead><tr><th>Source artifact</th><th>SHA-256</th></tr></thead><tbody>__SOURCE_ROWS__</tbody></table></div><div class="use-note"><strong>Portable by design.</strong> Anyone with a clone and the result artifacts can regenerate this file with <code>python3 scripts/build_evaluation_report.py</code>. It opens directly in a browser; the interactions use only embedded JavaScript, with no server, login, hosted API, external font, or package install required to read it. The normalized aggregate JSON is embedded in <code>#protofuse-report-data</code>.</div></div></details></section>

<footer class="footer"><span>Generated __GENERATED_AT__</span><span>Schema __SCHEMA_VERSION__ · missing values are labeled, never imputed</span></footer>
<script type="application/json" id="protofuse-report-data">__EMBEDDED_JSON__</script>
<script>
document.querySelectorAll('[data-tab-group]').forEach(function(group){
  var buttons=group.querySelectorAll('[data-tab]');
  var panels=group.querySelectorAll('[data-panel]');
  buttons.forEach(function(button){
    button.addEventListener('click',function(){
      var selected=button.getAttribute('data-tab');
      buttons.forEach(function(item){var active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-selected',String(active));});
      panels.forEach(function(panel){panel.classList.toggle('active',panel.getAttribute('data-panel')===selected);});
    });
  });
});
</script>
</body>
</html>
""".replace("__SCHEMA_VERSION__", REPORT_SCHEMA_VERSION)


def _resolve(root: Path, supplied: Path | None, default: str) -> Path:
    if supplied is None:
        return root / default
    return supplied if supplied.is_absolute() else root / supplied


def _export_slides_pdf(html_path: Path, pdf_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "PDF export requires playwright. Install with: "
            "uv sync --extra pdf && playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.emulate_media(media="print")
        slide_count = page.locator(".slide").count()
        if slide_count == 0:
            browser.close()
            raise SystemExit("slide deck HTML contains no .slide frames")

        if slide_count == 1:
            page.pdf(
                path=str(pdf_path),
                width="10in",
                height="5.625in",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            browser.close()
            return

        temp_paths: list[Path] = []
        try:
            for index in range(slide_count):
                page.evaluate(
                    """(activeIndex) => {
                        document.querySelectorAll('.slide').forEach((element, idx) => {
                            element.style.display = idx === activeIndex ? 'block' : 'none';
                        });
                        const deck = document.querySelector('.deck');
                        if (deck) {
                            deck.style.display = 'block';
                            deck.style.gap = '0';
                            deck.style.padding = '0';
                        }
                    }""",
                    index,
                )
                temp_path = pdf_path.with_suffix(f".{index:03d}.pdf")
                page.pdf(
                    path=str(temp_path),
                    width="10in",
                    height="5.625in",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
                temp_paths.append(temp_path)

            try:
                from pypdf import PdfWriter
            except ImportError as exc:
                raise SystemExit(
                    "Merging slide PDFs requires pypdf. Install with: uv sync --extra pdf"
                ) from exc

            writer = PdfWriter()
            for temp_path in temp_paths:
                writer.append(str(temp_path))
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
        finally:
            browser.close()
            for temp_path in temp_paths:
                temp_path.unlink(missing_ok=True)


def _resolve_slide_outputs(
    root: Path,
    output: Path | None,
    *,
    write_html: bool,
    write_pdf: bool,
) -> tuple[Path | None, Path | None]:
    default_html = root / "reports" / "protofuse-evaluation-slides.html"
    default_pdf = root / "reports" / "protofuse-evaluation-slides.pdf"
    if output is None:
        return (default_html if write_html else None, default_pdf if write_pdf else None)
    resolved = output if output.is_absolute() else root / output
    if write_html and write_pdf:
        if resolved.suffix.lower() == ".pdf":
            return default_html, resolved
        if resolved.suffix.lower() == ".html":
            return resolved, default_pdf
        return resolved.with_suffix(".html"), resolved.with_suffix(".pdf")
    if write_pdf:
        pdf_path = resolved if resolved.suffix.lower() == ".pdf" else resolved.with_suffix(".pdf")
        return None, pdf_path
    html_path = resolved if resolved.suffix.lower() == ".html" else resolved.with_suffix(".html")
    return html_path, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a self-contained ProtoFuse evaluation HTML report."
    )
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--analysis-dir", type=Path, default=None)
    parser.add_argument("--checkpoint-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if the Modal summary or surrogate pilot report is missing",
    )
    parser.add_argument(
        "--slides",
        action="store_true",
        help="write a 16:9 widescreen slide deck HTML instead of the scroll report",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="write a 16:9 widescreen slide deck PDF (one page per slide)",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    analysis_dir = _resolve(root, args.analysis_dir, "data/analysis")
    checkpoint_dir = _resolve(root, args.checkpoint_dir, "data/runs/checkpoints")
    output = (
        args.output
        if args.slides or args.pdf
        else _resolve(root, args.output, "reports/protofuse-evaluation.html")
    )
    required = [
        analysis_dir / "modal_smoke_summary.json",
        analysis_dir / "custom-egfp-lung" / "surrogate_pilot_report.json",
    ]
    missing = [path for path in required if not path.is_file()]
    if args.strict and missing:
        joined = ", ".join(str(path) for path in missing)
        raise SystemExit(f"missing required result artifacts: {joined}")
    data = collect_report_data(
        root,
        analysis_dir=analysis_dir,
        checkpoint_dir=checkpoint_dir,
    )
    if args.slides or args.pdf:
        slides_html = render_slides_html(data)
        html_output, pdf_output = _resolve_slide_outputs(
            root,
            output,
            write_html=args.slides,
            write_pdf=args.pdf,
        )
        temp_html: Path | None = None
        html_for_pdf: Path | None = None
        if html_output is not None:
            html_output.parent.mkdir(parents=True, exist_ok=True)
            html_output.write_text(slides_html, encoding="utf-8")
            print(f"wrote {html_output}")
            html_for_pdf = html_output
        if pdf_output is not None:
            pdf_output.parent.mkdir(parents=True, exist_ok=True)
            if html_for_pdf is None:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".html",
                    encoding="utf-8",
                    delete=False,
                ) as temp_file:
                    temp_file.write(slides_html)
                    temp_html = Path(temp_file.name)
                html_for_pdf = temp_html
            _export_slides_pdf(html_for_pdf, pdf_output)
            print(f"wrote {pdf_output}")
            if temp_html is not None:
                temp_html.unlink(missing_ok=True)
    else:
        scroll_output = _resolve(root, args.output, "reports/protofuse-evaluation.html")
        scroll_output.parent.mkdir(parents=True, exist_ok=True)
        scroll_output.write_text(render_report(data), encoding="utf-8")
        print(f"wrote {scroll_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
