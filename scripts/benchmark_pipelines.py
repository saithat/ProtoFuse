#!/usr/bin/env -S uv run python
"""Benchmark Phillip pipelines locally and on Modal at the smoke tier.

Smoke is the validation bar for Phillip: one `program.run()` per collection, enough to
prove bindings execute on GPU. Full-tier and paper-length timings belong to Sai, so the
minute-scale CPU loops are opt-in via `--full`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
# One file per invocation, so concurrent sessions never overwrite each other's rows.
RUNS_DIR = REPO_ROOT / "workspaces/phillip/benchmark_runs"
RECORD_MD = REPO_ROOT / "workspaces/phillip/PIPELINE_BENCHMARKS.md"


def _load_repo_env() -> None:
    from protofuse.env import load_repo_env

    load_repo_env()

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
    run_path: Path | None = None

    def add(self, record: RunRecord) -> None:
        self.runs.append(record)
        # Flush per row: a GPU pipeline can hang for hours, and rows already earned
        # should survive a kill.
        self.flush()

    def flush(self) -> None:
        if self.run_path is None:
            return
        self.run_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_path.write_text(json.dumps(self.to_json(), indent=2) + "\n")

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
    from protofuse.phillip.handoff_config import run_compiled_program

    path = REPO_ROOT / "proto_programs/generated" / collection_id / design_file
    spec = importlib.util.spec_from_file_location(f"{collection_id}_{design_file}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    program = module.build_program()
    run_compiled_program(program, fixture_id=collection_id)
    joined = program.constructs[0].joined_sequences
    lengths = [len(item.sequence) for item in joined]
    return {"design": design_file, "output_lengths": lengths, "num_results": len(joined)}


EXEC_RESULT_MARKER = "__BENCH_EXEC_RESULT__ "


def run_design_isolated(
    collection_id: str, design_file: str, timeout: float | None
) -> dict[str, Any]:
    """Execute one design in a child process so a stuck GPU call can be killed cleanly.

    `on_demand_modal_tools()` configures a *process-global* dispatch backend. Abandoning a
    hung call in-process leaves that backend engaged, and every later pipeline then dies on
    "another dispatch backend is configured", so isolation has to be a process boundary.
    """

    argv = [sys.executable, str(Path(__file__).resolve()), "--exec-one", collection_id, design_file]
    try:
        proc = subprocess.run(
            argv, cwd=REPO_ROOT, text=True, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"killed after {timeout:.0f}s with no result") from None

    for line in proc.stdout.splitlines():
        if line.startswith(EXEC_RESULT_MARKER):
            return json.loads(line[len(EXEC_RESULT_MARKER) :])

    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    raise RuntimeError(detail[-1] if detail else f"child exited {proc.returncode} with no result")


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
        reason="Not included in this benchmark path; run the supported CLI preflight separately",
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
    exec_timeout: float | None = None,
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
            fn=lambda: run_design_isolated(fixture_id, design_file, exec_timeout),
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
    exec_timeout: float | None = None,
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
        fn=lambda: run_design_isolated(pipeline, design_file, exec_timeout),
        notes=notes,
    )


def run_file_path(recorded_at: str) -> Path:
    """Unique destination for one invocation, so concurrent runs cannot collide."""

    stamp = recorded_at.replace(":", "").replace("-", "").split(".")[0]
    return RUNS_DIR / f"run-{stamp}-{os.getpid()}.json"


def load_rollup() -> dict[str, Any]:
    """Merge every per-run file, keeping the newest result per (pipeline, run_id, device)."""

    files = sorted(RUNS_DIR.glob("run-*.json")) if RUNS_DIR.is_dir() else []
    if not files:
        raise ValueError(f"no benchmark runs found under {RUNS_DIR}")

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    latest: dict[str, Any] = {}
    for path in files:
        payload = json.loads(path.read_text())
        if payload.get("recorded_at", "") >= latest.get("recorded_at", ""):
            latest = payload
        for run in payload["runs"]:
            key = (run["pipeline"], run["run_id"], run["device"])
            previous = merged.get(key)
            if previous is None or payload["recorded_at"] >= previous["_recorded_at"]:
                merged[key] = {**run, "_recorded_at": payload["recorded_at"]}

    runs = sorted(merged.values(), key=lambda item: (item["pipeline"], item["run_id"]))
    return {
        "schema_version": "1.1",
        "recorded_at": latest.get("recorded_at", ""),
        "environment": latest.get("environment", {}),
        "run_files": [path.name for path in files],
        "runs": runs,
    }


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
        "uv run python scripts/benchmark_pipelines.py --write-markdown",
        "uv run python scripts/benchmark_pipelines.py --skip-modal-exec   # CPU only",
        "uv run python scripts/benchmark_pipelines.py --rollup-only --write-markdown",
        "```",
        "",
        "Scope: **smoke tier only** — one `program.run()` per collection, enough to prove",
        "bindings execute on GPU. Full-tier and paper-length timings are Sai's; absent",
        "full-tier rows are expected, not a gap (`--full` opts in).",
        "",
        "Rows are merged from per-invocation files in `benchmark_runs/` (newest wins per",
        f"pipeline/run/device), so concurrent sessions do not overwrite each other. "
        f"This summary merges {len(data.get('run_files', []))} run file(s); raw runs are"
        " gitignored.",
        "",
        "This file is a timestamped run record, not a current feature matrix. A `skipped` "
        "row records only what this benchmark invocation omitted.",
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
            "The filenames below are ordinal IDs. This snapshot's two-program collections "
            "map `001` to full and `002` to smoke, but use each generated module's docstring "
            "as the authority.",
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
    _load_repo_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run minute-scale full-tier CPU loops (Sai's scope; off by default)",
    )
    parser.add_argument(
        "--skip-full",
        action="store_true",
        help="accepted for compatibility; full tiers are already off by default",
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
    parser.add_argument(
        "--exec-timeout",
        type=float,
        default=900.0,
        help=(
            "seconds to wait for one Modal execute before recording a timeout and moving on "
            "(0 disables; smoke runs should never need hours)"
        ),
    )
    parser.add_argument(
        "--write-markdown",
        action="store_true",
        help="regenerate PIPELINE_BENCHMARKS.md from all per-run files",
    )
    parser.add_argument(
        "--rollup-only",
        action="store_true",
        help="rebuild the rollup from existing per-run files without benchmarking",
    )
    parser.add_argument(
        "--exec-one",
        nargs=2,
        metavar=("COLLECTION_ID", "DESIGN_FILE"),
        help="internal: execute one design in this process and print its result",
    )
    args = parser.parse_args()

    if args.exec_one:
        collection_id, design_file = args.exec_one
        result = run_design_program(collection_id, design_file)
        print(EXEC_RESULT_MARKER + json.dumps(result))
        return 0

    if args.rollup_only:
        rollup = load_rollup()
        if args.write_markdown:
            RECORD_MD.write_text(render_markdown(rollup))
            print(f"wrote {RECORD_MD.relative_to(REPO_ROOT)}")
        else:
            print(
                f"merged {len(rollup['runs'])} rows from "
                f"{len(rollup['run_files'])} run file(s); pass --write-markdown to render"
            )
        return 0

    recorded_at = datetime.now(tz=UTC).isoformat()
    record = BenchmarkRecord(
        recorded_at=recorded_at,
        environment={
            "host": platform.node(),
            "platform": platform.platform(),
            "proto_version": git_head(),
            "modal_profile": modal_profile() or "",
        },
        run_path=run_file_path(recorded_at),
    )
    exec_timeout = args.exec_timeout or None

    benchmark_cpu_pipelines(record, include_full=args.full)
    benchmark_gpu_collection(
        record,
        fixture_id="esm2-protein-maturation",
        registry_name="esm2-protein-maturation",
        preflight_length=80,
        preflight_notes="80 aa smoke segment; build-only L0",
        execute_notes="ESM-2 + ESMFold on Modal (smoke: 80 aa, 50 MCMC steps)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="antibody-cdr-maturation",
        registry_name="antibody-cdr-maturation",
        preflight_length=121,
        preflight_notes="121 aa nanobody framework; build-only L0",
        execute_notes="ESM-2 + AbLang + ESMFold on Modal (smoke: CDR1, 30 steps)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="freebindcraft-binder",
        registry_name="freebindcraft-binder",
        preflight_length=50,
        preflight_notes="50 aa smoke binder; build-only L0",
        execute_notes="FreeBindCraft + AF2 validation on Modal (smoke: 5 samples)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="symmetric-oligomer-ring",
        registry_name="symmetric-oligomer-ring",
        preflight_length=60,
        preflight_notes="60 aa C3 monomer smoke; build-only L0",
        execute_notes="Symmetry + ESMFold composite on Modal (smoke: pool=100)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="ppi-interface-specificity",
        registry_name="ppi-interface-specificity",
        preflight_length=65,
        preflight_notes="65 aa binder seed; build-only L0",
        execute_notes="Dual target/off-target scoring on Modal (smoke: 20 MCMC steps)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="rfdiffusion3-boltz2-binder",
        registry_name="rfdiffusion3-boltz2-binder",
        preflight_length=50,
        preflight_notes="50 aa smoke binder; build-only L0",
        execute_notes="RFdiffusion3 bootstrap + Boltz-2 cycling on Modal (smoke: 2 cycles)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="ligandmpnn-enzyme-redesign",
        registry_name="ligandmpnn-enzyme-redesign",
        preflight_length=163,
        preflight_notes="3HTB holo enzyme; build-only L0",
        execute_notes="LigandMPNN active-site MCMC on Modal (smoke: 20 steps)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
    )
    benchmark_gpu_collection(
        record,
        fixture_id="bioemu-ensemble-filter",
        registry_name="bioemu-ensemble-filter",
        preflight_length=80,
        preflight_notes="80 aa lysozyme smoke segment; build-only L0",
        execute_notes="BioEmu ensemble RMSD + ESM-2 on Modal (smoke: 20 steps, 2 samples)",
        skip_modal_exec=args.skip_modal_exec,
        exec_timeout=exec_timeout,
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
            exec_timeout=exec_timeout,
        )

    record.flush()
    print(f"\nwrote {record.run_path.relative_to(REPO_ROOT)}")
    if args.write_markdown:
        RECORD_MD.write_text(render_markdown(load_rollup()))
        print(f"wrote {RECORD_MD.relative_to(REPO_ROOT)}")
    else:
        print("markdown not regenerated; pass --write-markdown to refresh the rollup")
    failed = sum(1 for item in record.runs if item.status == "failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
