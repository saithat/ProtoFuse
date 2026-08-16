#!/usr/bin/env -S uv run python
"""Benchmark all Phillip pipelines locally and on Modal; write a consolidated record."""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_JSON = REPO_ROOT / "workspaces/phillip/PIPELINE_BENCHMARKS.json"
RECORD_MD = REPO_ROOT / "workspaces/phillip/PIPELINE_BENCHMARKS.md"

RunStatus = Literal["ok", "failed", "skipped"]


@dataclass
class RunRecord:
    run_id: str
    pipeline: str
    device: Literal["local", "modal"]
    kind: str
    command: str
    status: RunStatus
    wall_ms: float | None = None
    output_summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    notes: str | None = None


@dataclass
class BenchmarkRecord:
    schema_version: str = "1.0"
    recorded_at: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    runs: list[RunRecord] = field(default_factory=list)

    def add(self, record: RunRecord) -> None:
        self.runs.append(record)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recorded_at": self.recorded_at,
            "environment": self.environment,
            "runs": [asdict(item) for item in self.runs],
        }


def git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True)
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def modal_profile() -> str | None:
    try:
        output = subprocess.check_output(
            ["uv", "run", "modal", "profile", "list"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in output.splitlines():
        if "│" not in line or "Profile" in line or "───" in line:
            continue
        parts = [part.strip() for part in line.split("│") if part.strip()]
        if not parts:
            continue
        profile = parts[0].lstrip("• ").strip()
        if profile and profile != "Profile":
            return profile
    return "configured"


def timed_run(
    record: BenchmarkRecord,
    *,
    run_id: str,
    pipeline: str,
    device: Literal["local", "modal"],
    kind: str,
    command: str,
    fn,
    notes: str | None = None,
) -> Any:
    started = perf_counter()
    try:
        result = fn()
        wall_ms = round((perf_counter() - started) * 1000, 3)
        summary = result if isinstance(result, dict) else {}
        record.add(
            RunRecord(
                run_id=run_id,
                pipeline=pipeline,
                device=device,
                kind=kind,
                command=command,
                status="ok",
                wall_ms=wall_ms,
                output_summary=summary,
                notes=notes,
            )
        )
        print(f"ok  {run_id}: {wall_ms:.0f} ms")
        return result
    except Exception as exc:  # noqa: BLE001 - benchmark harness
        wall_ms = round((perf_counter() - started) * 1000, 3)
        record.add(
            RunRecord(
                run_id=run_id,
                pipeline=pipeline,
                device=device,
                kind=kind,
                command=command,
                status="failed",
                wall_ms=wall_ms,
                error=str(exc),
                notes=notes,
            )
        )
        print(f"fail {run_id}: {exc}", file=sys.stderr)
        return None


def skip_run(
    record: BenchmarkRecord,
    *,
    run_id: str,
    pipeline: str,
    device: Literal["local", "modal"],
    kind: str,
    command: str,
    reason: str,
) -> None:
    record.add(
        RunRecord(
            run_id=run_id,
            pipeline=pipeline,
            device=device,
            kind=kind,
            command=command,
            status="skipped",
            notes=reason,
        )
    )
    print(f"skip {run_id}: {reason}")


def run_compile(
    fixture_id: str,
    registry_name: str,
    device: Literal["local", "modal"],
) -> dict[str, Any]:
    from protofuse.phillip import compile_proto_plan, recommend_topologies
    from protofuse.phillip.program_builders import load_fixture_spec
    from protofuse.phillip.registries import lookup_registry

    spec_path = REPO_ROOT / "workspaces/phillip/fixtures" / fixture_id / "methodology.json"
    spec = load_fixture_spec(fixture_id)
    recommendations = recommend_topologies(spec)
    plan = compile_proto_plan(
        spec,
        recommendations[0],
        registry=lookup_registry(registry_name),
        device=device,
    )
    return {
        "fixture": fixture_id,
        "device": device,
        "executable": plan.executable,
        "unresolved": plan.unresolved,
        "methodology_path": str(spec_path.relative_to(REPO_ROOT)),
    }


def run_design_program(collection_id: str, design_file: str) -> dict[str, Any]:
    path = REPO_ROOT / "proto_programs/generated" / collection_id / design_file
    spec = importlib.util.spec_from_file_location(f"{collection_id}_{design_file}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    program = module.build_program()
    program.run()
    joined = program.constructs[0].joined_sequences
    lengths = [len(item.sequence) for item in joined]
    return {"design": design_file, "output_lengths": lengths, "num_results": len(joined)}


def benchmark_cpu_pipelines(record: BenchmarkRecord, *, include_full: bool) -> None:
    import logging

    logging.disable(logging.CRITICAL)

    from protofuse.phillip.program_builders import run_custom_egfp_lung, run_dnachisel_num1
    from protofuse.phillip.workload_preflight import run_preflight

    pipeline = "dnachisel-num1"
    timed_run(
        record,
        run_id="preflight_2808",
        pipeline=pipeline,
        device="local",
        kind="preflight",
        command="uv run protofuse preflight dnachisel-num1 --length 2808",
        fn=lambda: {
            "classification": run_preflight(
                "dnachisel-num1", target_length=2808, filter_samples=200, num_steps=30
            ).classification
        },
        notes="Paper construct length binding ladder",
    )
    timed_run(
        record,
        run_id="preflight_936",
        pipeline=pipeline,
        device="local",
        kind="preflight",
        command="uv run protofuse preflight dnachisel-num1 --length 936 --strict",
        fn=lambda: {
            "classification": run_preflight(
                "dnachisel-num1", target_length=936, filter_samples=500, num_steps=50
            ).classification
        },
        notes="Executable fixture length",
    )
    timed_run(
        record,
        run_id="outer_loop_smoke",
        pipeline=pipeline,
        device="local",
        kind="execute",
        command="uv run protofuse run dnachisel-num1 --tier smoke",
        fn=lambda: _run_dnachisel(run_dnachisel_num1, "smoke"),
        notes="100 bp, 1 region pass",
    )
    if include_full:
        timed_run(
            record,
            run_id="outer_loop_full",
            pipeline=pipeline,
            device="local",
            kind="execute",
            command="uv run protofuse run dnachisel-num1 --tier full",
            fn=lambda: _run_dnachisel(run_dnachisel_num1, "full"),
            notes="936 bp, region-local solver — primary Sai target",
        )

    for device in ("local", "modal"):
        timed_run(
            record,
            run_id=f"compile_{device}",
            pipeline=pipeline,
            device=device,  # type: ignore[arg-type]
            kind="compile_plan",
            command=(
                f"uv run protofuse compile workspaces/phillip/fixtures/dnachisel-num1/"
                f"methodology.json --registry dnachisel-num1 --device {device}"
            ),
            fn=lambda device=device: run_compile("dnachisel-num1", "dnachisel-num1", device),  # type: ignore[arg-type]
            notes="Plan metadata only; MCMC executes locally regardless",
        )

    pipeline = "custom-egfp-lung"
    timed_run(
        record,
        run_id="outer_loop_smoke",
        pipeline=pipeline,
        device="local",
        kind="execute",
        command="uv run protofuse run custom-egfp-lung --tier smoke",
        fn=lambda: _run_custom_egfp(run_custom_egfp_lung, "smoke"),
        notes="720 bp, n_pool smoke defaults",
    )
    if include_full:
        timed_run(
            record,
            run_id="outer_loop_full",
            pipeline=pipeline,
            device="local",
            kind="execute",
            command="uv run protofuse run custom-egfp-lung --tier full",
            fn=lambda: _run_custom_egfp(run_custom_egfp_lung, "full"),
            notes="720 bp, n_pool=1000 — primary Sai target",
        )
    skip_run(
        record,
        run_id="preflight",
        pipeline=pipeline,
        device="local",
        kind="preflight",
        command="uv run protofuse preflight custom-egfp-lung",
        reason="CLI preflight not implemented for this fixture",
    )
    for device in ("local", "modal"):
        timed_run(
            record,
            run_id=f"compile_{device}",
            pipeline=pipeline,
            device=device,  # type: ignore[arg-type]
            kind="compile_plan",
            command=(
                f"uv run protofuse compile workspaces/phillip/fixtures/custom-egfp-lung/"
                f"methodology.json --registry custom-egfp --device {device}"
            ),
            fn=lambda device=device: run_compile("custom-egfp-lung", "custom-egfp", device),  # type: ignore[arg-type]
            notes="Plan metadata only; pool loop executes locally regardless",
        )


def _run_dnachisel(fn, tier: str) -> dict[str, Any]:
    program, wall_ms = fn(tier=tier)
    sequence = program.constructs[0].joined_sequences[0].sequence
    return {"tier": tier, "wall_ms": round(wall_ms, 3), "output_length_bp": len(sequence)}


def _run_custom_egfp(fn, tier: str) -> dict[str, Any]:
    program, wall_ms = fn(tier=tier)
    sequence = program.constructs[0].joined_sequences[0].sequence
    return {"tier": tier, "wall_ms": round(wall_ms, 3), "output_length_bp": len(sequence)}


def benchmark_gpu_collection(
    record: BenchmarkRecord,
    *,
    fixture_id: str,
    registry_name: str,
    preflight_length: int,
    preflight_notes: str,
    execute_notes: str,
    skip_modal_exec: bool,
    design_file: str = "design_002.py",
) -> None:
    """Preflight, handoff generate, compile, and optional Modal execute for a GPU fixture."""

    import logging

    from protofuse.phillip.handoff_pipeline import run_handoff_pipeline
    from protofuse.phillip.workload_preflight import run_preflight

    logging.disable(logging.CRITICAL)
    pipeline = fixture_id

    timed_run(
        record,
        run_id="preflight_smoke",
        pipeline=pipeline,
        device="local",
        kind="preflight",
        command=f"uv run protofuse preflight {fixture_id} --length {preflight_length}",
        fn=lambda: {
            "classification": run_preflight(
                fixture_id,
                target_length=preflight_length,
            ).classification
        },
        notes=preflight_notes,
    )
    timed_run(
        record,
        run_id="handoff_pipeline",
        pipeline=pipeline,
        device="local",
        kind="handoff_generate",
        command=f"uv run python scripts/run_handoff_pipeline.py {fixture_id}",
        fn=lambda: _run_generic_handoff(fixture_id, run_handoff_pipeline),
        notes="compile → generate → finalize via run_handoff_pipeline",
    )
    for device in ("local", "modal"):
        timed_run(
            record,
            run_id=f"compile_{device}",
            pipeline=pipeline,
            device=device,  # type: ignore[arg-type]
            kind="compile_plan",
            command=(
                f"uv run protofuse compile workspaces/phillip/fixtures/{fixture_id}/"
                f"methodology.json --registry {registry_name} --device {device}"
            ),
            fn=lambda device=device: run_compile(fixture_id, registry_name, device),  # type: ignore[arg-type]
            notes="GPU constraints require Modal at program.run() time",
        )
    if skip_modal_exec:
        skip_run(
            record,
            run_id="execute_smoke",
            pipeline=pipeline,
            device="modal",
            kind="execute",
            command=f"build_program().run() via {design_file}",
            reason="--skip-modal-exec",
        )
    else:
        timed_run(
            record,
            run_id="execute_smoke",
            pipeline=pipeline,
            device="modal",
            kind="execute",
            command=f"build_program().run() via {design_file}",
            fn=lambda: run_design_program(fixture_id, design_file),
            notes=execute_notes,
        )


def _run_generic_handoff(fixture_id: str, run_fn) -> dict[str, Any]:
    timing = run_fn(fixture_id)
    return {
        "total_elapsed_s": timing["total_elapsed_s"],
        "topology": timing["topology"],
        "handoff_path": timing["handoff_path"],
    }


def benchmark_gpcr_handoff(record: BenchmarkRecord) -> None:
    pipeline = "gpcr-cxcr4-miniprotein"
    timed_run(
        record,
        run_id="handoff_pipeline",
        pipeline=pipeline,
        device="local",
        kind="handoff_generate",
        command="uv run python scripts/run_gpcr_cxcr4_pipeline.py",
        fn=_run_gpcr_handoff,
        notes="Paper ingest → compile (device=modal on plan) → generate → finalize",
    )
    for device in ("local", "modal"):
        timed_run(
            record,
            run_id=f"compile_{device}",
            pipeline=pipeline,
            device=device,  # type: ignore[arg-type]
            kind="compile_plan",
            command=(
                f"uv run protofuse compile workspaces/phillip/fixtures/gpcr-cxcr4-miniprotein/"
                f"methodology.json --registry gpcr-cxcr4 --device {device}"
            ),
            fn=lambda device=device: run_compile("gpcr-cxcr4-miniprotein", "gpcr-cxcr4", device),  # type: ignore[arg-type]
            notes="Full tier requires Modal GPU tools at program.run() time",
        )


def _run_gpcr_handoff() -> dict[str, Any]:
    timing_path = REPO_ROOT / "workspaces/phillip/TIMING_gpcr-cxcr4-miniprotein.json"
    before = timing_path.read_text() if timing_path.is_file() else None
    subprocess.check_call(
        [sys.executable, str(REPO_ROOT / "scripts/run_gpcr_cxcr4_pipeline.py")],
        cwd=REPO_ROOT,
    )
    timing = json.loads(timing_path.read_text())
    timing["regenerated"] = before != timing_path.read_text()
    return {
        "total_elapsed_s": timing["total_elapsed_s"],
        "topology": timing["topology"],
        "handoff_path": timing["handoff_path"],
    }


def benchmark_gpcr_modal_exec(
    record: BenchmarkRecord,
    *,
    design_file: str,
    run_id: str,
    notes: str,
) -> None:
    pipeline = "gpcr-cxcr4-miniprotein"
    timed_run(
        record,
        run_id=run_id,
        pipeline=pipeline,
        device="modal",
        kind="execute",
        command=(
            f"uv run python -c \"import ...; build_program().run()\" "
            f"({design_file})"
        ),
        fn=lambda: run_design_program(pipeline, design_file),
        notes=notes,
    )


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Pipeline benchmarks (all Phillip workloads)",
        "",
        f"**Recorded:** {data['recorded_at']}",
        f"**Proto commit:** `{data['environment'].get('proto_version', 'unknown')}`",
        f"**Host:** {data['environment'].get('host', 'unknown')}",
        f"**Modal profile:** {data['environment'].get('modal_profile') or 'not configured'}",
        "",
        "Re-run:",
        "",
        "```bash",
        "uv run python scripts/benchmark_pipelines.py",
        "uv run python scripts/benchmark_pipelines.py --skip-modal-exec   # CPU only",
        "```",
        "",
        "Machine-readable record: [`PIPELINE_BENCHMARKS.json`](PIPELINE_BENCHMARKS.json).",
        "",
        "Per-pipeline handoff timing notes:",
        "",
        "- [`TIMING_gpcr-cxcr4-miniprotein.json`](TIMING_gpcr-cxcr4-miniprotein.json)",
        "- [`TIMING_esm2-protein-maturation.json`](TIMING_esm2-protein-maturation.json)",
        "- [`TIMING_antibody-cdr-maturation.json`](TIMING_antibody-cdr-maturation.json)",
        "- [`TIMING_freebindcraft-binder.json`](TIMING_freebindcraft-binder.json)",
        "- [`TIMING_symmetric-oligomer-ring.json`](TIMING_symmetric-oligomer-ring.json)",
        "- [`TIMING_ppi-interface-specificity.json`](TIMING_ppi-interface-specificity.json)",
        "",
        "## Summary",
        "",
        "| Pipeline | Run | Device | Status | Wall time | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in data["runs"]:
        wall = item.get("wall_ms")
        wall_text = f"{wall / 1000:.1f} s" if wall is not None else "—"
        note = item.get("notes") or ""
        if item.get("status") == "failed" and item.get("error"):
            err = str(item["error"]).split("\n")[0]
            note = f"{note} — {err}" if note else err
        elif not note:
            note = item.get("error") or ""
        lines.append(
            f"| `{item['pipeline']}` | `{item['run_id']}` | {item['device']} | "
            f"{item['status']} | {wall_text} | {note} |"
        )

    lines.extend(
        [
            "",
            "## Primary programs for Sai",
            "",
            "| Collection | Profile this | Skip |",
            "| --- | --- | --- |",
            "| `dnachisel-num1` | `design_001.py` (936 bp full outer loop) "
            "| `design_002.py` smoke |",
            "| `custom-egfp-lung` | `design_001.py` (720 bp full pool) "
            "| `design_002.py` smoke |",
            "| `esm2-protein-maturation` | `design_001.py` (129 aa lysozyme, 200 steps) "
            "| `design_002.py` smoke |",
            "| `antibody-cdr-maturation` | `design_001.py` (121 aa, 3 CDR passes) "
            "| `design_002.py` smoke |",
            "| `freebindcraft-binder` | `design_001.py` (70 aa, 50 samples) "
            "| `design_002.py` smoke |",
            "| `symmetric-oligomer-ring` | `design_001.py` (C6, pool=1000) "
            "| `design_002.py` smoke |",
            "| `ppi-interface-specificity` | `design_001.py` (100 steps, MPNN) "
            "| `design_002.py` smoke |",
            "| `gpcr-cxcr4-miniprotein` | `design_001.py` (70 aa, 10 samples) "
            "| `design_002.py` unless debugging |",
            "",
            "## Modal vs local",
            "",
            "- **CPU codon workloads** (`dnachisel-num1`, `custom-egfp-lung`): execution is always "
            "local CPU. `--device modal` on `protofuse compile` only tags the plan.",
            "- **GPU protein workloads** (`esm2-protein-maturation`, "
            "`antibody-cdr-maturation`, `gpcr-cxcr4-miniprotein`): "
            '`compile_proto_plan(..., device="modal")` matches runtime — `program.run()` '
            "invokes ESM-2/ESMFold, AbLang, RFdiffusion3, or Boltz-2 on Modal GPUs.",
            "",
            "Detailed node profiles for Sai belong under `data/analysis/<collection_id>/` "
            "(gitignored). This file records orchestrator-level wall times only.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-full",
        action="store_true",
        help="skip minute-scale full-tier CPU runs",
    )
    parser.add_argument(
        "--skip-modal-exec",
        action="store_true",
        help="skip GPU design program.run() on Modal (esm2, antibody, GPCR)",
    )
    parser.add_argument(
        "--gpcr-design",
        default="design_002.py",
        help="GPCR collection program to execute on Modal (default: smoke tier)",
    )
    args = parser.parse_args()

    record = BenchmarkRecord(
        recorded_at=datetime.now(tz=UTC).isoformat(),
        environment={
            "host": platform.node(),
            "platform": platform.platform(),
            "proto_version": git_head(),
            "modal_profile": modal_profile() or "",
        },
    )

    benchmark_cpu_pipelines(record, include_full=not args.skip_full)
    benchmark_gpu_collection(
        record,
        fixture_id="esm2-protein-maturation",
        registry_name="esm2-protein-maturation",
        preflight_length=80,
        preflight_notes="80 aa smoke segment; build-only L0",
        execute_notes="ESM-2 + ESMFold on Modal (smoke: 80 aa, 50 MCMC steps)",
        skip_modal_exec=args.skip_modal_exec,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="antibody-cdr-maturation",
        registry_name="antibody-cdr-maturation",
        preflight_length=121,
        preflight_notes="121 aa nanobody framework; build-only L0",
        execute_notes="ESM-2 + AbLang + ESMFold on Modal (smoke: CDR1, 30 steps)",
        skip_modal_exec=args.skip_modal_exec,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="freebindcraft-binder",
        registry_name="freebindcraft-binder",
        preflight_length=50,
        preflight_notes="50 aa smoke binder; build-only L0",
        execute_notes="FreeBindCraft + AF2 validation on Modal (smoke: 5 samples)",
        skip_modal_exec=args.skip_modal_exec,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="symmetric-oligomer-ring",
        registry_name="symmetric-oligomer-ring",
        preflight_length=60,
        preflight_notes="60 aa C3 monomer smoke; build-only L0",
        execute_notes="Symmetry + ESMFold composite on Modal (smoke: pool=100)",
        skip_modal_exec=args.skip_modal_exec,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="ppi-interface-specificity",
        registry_name="ppi-interface-specificity",
        preflight_length=65,
        preflight_notes="65 aa binder seed; build-only L0",
        execute_notes="Dual target/off-target scoring on Modal (smoke: 20 MCMC steps)",
        skip_modal_exec=args.skip_modal_exec,
    )
    benchmark_gpcr_handoff(record)
    if args.skip_modal_exec:
        skip_run(
            record,
            run_id="execute_smoke",
            pipeline="gpcr-cxcr4-miniprotein",
            device="modal",
            kind="execute",
            command=f"build_program().run() via {args.gpcr_design}",
            reason="--skip-modal-exec",
        )
    else:
        benchmark_gpcr_modal_exec(
            record,
            design_file=args.gpcr_design,
            run_id="execute_smoke" if args.gpcr_design == "design_002.py" else "execute_full",
            notes="RFdiffusion3 + ProteinMPNN + Boltz-2 on Modal",
        )

    data = record.to_json()
    RECORD_JSON.write_text(json.dumps(data, indent=2) + "\n")
    RECORD_MD.write_text(render_markdown(data))
    print(f"\nwrote {RECORD_JSON.relative_to(REPO_ROOT)}")
    print(f"wrote {RECORD_MD.relative_to(REPO_ROOT)}")
    failed = sum(1 for item in record.runs if item.status == "failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
