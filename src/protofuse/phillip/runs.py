"""Layout and persistence for gitignored benchmark runs under data/runs/."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

RunVariant = Literal["baseline", "candidate"]

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_ROOT = REPO_ROOT / "data" / "runs"
HANDOFF_ROOT = REPO_ROOT / "philip-sai-workflow-dump"


def decision_runs_dir(decision_id: str) -> Path:
    return RUNS_ROOT / decision_id


def variant_dir(decision_id: str, variant: RunVariant) -> Path:
    return decision_runs_dir(decision_id) / variant


def phillip_handoff_dir(decision_id: str) -> Path:
    return HANDOFF_ROOT / "phillip_to_sai" / decision_id


def sai_handoff_dir(decision_id: str) -> Path:
    return HANDOFF_ROOT / "sai_to_phillip" / decision_id


def new_run_id() -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    variant: RunVariant
    decision_id: str
    scenario_id: str
    seed: int
    device: str
    run_dir: Path


def write_run_manifest(decision_id: str, manifest: dict[str, Any]) -> Path:
    out = decision_runs_dir(decision_id) / "run_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return out


def load_run_manifest(decision_id: str) -> dict[str, Any]:
    path = decision_runs_dir(decision_id) / "run_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing run manifest: {path}")
    return json.loads(path.read_text())


def write_run_artifacts(run_dir: Path, artifacts: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        (run_dir / name).write_text(json.dumps(payload, indent=2) + "\n")


def list_run_dirs(decision_id: str, variant: RunVariant) -> list[Path]:
    root = variant_dir(decision_id, variant)
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())
