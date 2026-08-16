"""Fail-closed worker for the pinned AlphaFold 3 pair-scaling patch.

The worker deliberately invokes only a verified, locally patched checkout of
official AlphaFold 3 v3.0.1.  It does not support an opaque SIF or fall back to
an unmodified model.  The patch's model runner checks a JAX loop-carried hook
count for every seed before the official CLI can return successfully.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

AF3_UPSTREAM_COMMIT = "231efc9bb9c13b45cc59e43f7107869084ee9624"
AF3_UPSTREAM_TAG = "v3.0.1"
PAIR_SCALING_PATCH_SHA256 = (
    "339c4f9f9a8fe607eb01c6e898a57ee3d03b1823b40d8efe99c02e6a8d0cfead"
)
PATCHED_SOURCE_SHA256: dict[str, str] = {
    "run_alphafold.py": "950c4f9b4ebe4265a69b361d76f755268274da023e5fa0f01f2255734b0c09b9",
    "src/alphafold3/model/model.py": (
        "eb6a1901015c14b40ef22e6fcec45f2df61f0b93780776013e3ef12c526805ac"
    ),
    "src/alphafold3/model/network/evoformer.py": (
        "671d49e0c6b548842dc17d1144096f35dbbe31223d4ea7a9a6ffe056945ca8ac"
    ),
}
ALLOWED_PAIR_SCALING_BETAS: tuple[float, ...] = (
    -0.75,
    -0.60,
    -0.45,
    -0.30,
    -0.15,
    0.0,
    0.15,
    0.30,
    0.45,
    0.60,
    0.75,
)


class PairScaledAlphaFold3Error(RuntimeError):
    """Raised when the verified pair-scaled AF3 path cannot be used."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_beta(value: object) -> float:
    """Return the canonical paper-sweep beta or reject the request."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("AlphaFold 3 pair-scaling beta must be a number")
    beta = float(value)
    if not math.isfinite(beta):
        raise ValueError("AlphaFold 3 pair-scaling beta must be finite")
    for allowed in ALLOWED_PAIR_SCALING_BETAS:
        if math.isclose(beta, allowed, rel_tol=0.0, abs_tol=1e-12):
            return allowed
    raise ValueError(
        f"unsupported AlphaFold 3 pair-scaling beta {beta}; "
        f"expected one of {ALLOWED_PAIR_SCALING_BETAS}"
    )


def scale_pairformer_input_for_audit(value: Any, beta: object) -> Any:
    """Mirror the parameter-free patch operation for isolated parity tests."""

    canonical_beta = validate_beta(beta)
    if canonical_beta == 0.0:
        return value
    return value * (1.0 + canonical_beta)


def expected_pair_scaling_invocations(num_recycles: object) -> int:
    """Return AF3's trunk-pass count: initial pass plus configured recycles."""

    if isinstance(num_recycles, bool) or not isinstance(num_recycles, int):
        raise ValueError("AlphaFold 3 num_recycles must be an integer")
    if num_recycles < 0:
        raise ValueError("AlphaFold 3 num_recycles must be non-negative")
    return num_recycles + 1


def verify_patch_artifact(patch_path: str | os.PathLike[str]) -> Path:
    """Verify the exact reviewed patch bytes before trusting the checkout."""

    resolved = Path(patch_path).resolve()
    if not resolved.is_file():
        raise PairScaledAlphaFold3Error(f"AlphaFold 3 patch not found: {resolved}")
    actual = _sha256_file(resolved)
    if actual != PAIR_SCALING_PATCH_SHA256:
        raise PairScaledAlphaFold3Error(
            "AlphaFold 3 pair-scaling patch digest mismatch: "
            f"observed {actual}, expected {PAIR_SCALING_PATCH_SHA256}"
        )
    return resolved


def _git_head(checkout: Path) -> str | None:
    if not (checkout / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise PairScaledAlphaFold3Error(
            "could not verify the AlphaFold 3 checkout commit"
        ) from error
    if completed.returncode != 0:
        raise PairScaledAlphaFold3Error(
            "could not read the AlphaFold 3 checkout commit: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def verify_patched_checkout(
    alphafold3_root: str | os.PathLike[str],
    patch_path: str | os.PathLike[str],
) -> Path:
    """Verify the upstream commit when available and every patched source blob."""

    verify_patch_artifact(patch_path)
    checkout = Path(alphafold3_root).resolve()
    if not checkout.is_dir():
        raise PairScaledAlphaFold3Error(
            f"AlphaFold 3 checkout not found: {checkout}"
        )

    head = _git_head(checkout)
    if head is not None and head != AF3_UPSTREAM_COMMIT:
        raise PairScaledAlphaFold3Error(
            f"unsupported AlphaFold 3 commit {head}; expected {AF3_UPSTREAM_COMMIT}"
        )

    for relative, expected_digest in PATCHED_SOURCE_SHA256.items():
        source = checkout / relative
        if not source.is_file():
            raise PairScaledAlphaFold3Error(
                f"patched AlphaFold 3 source is missing: {source}"
            )
        actual_digest = _sha256_file(source)
        if actual_digest != expected_digest:
            raise PairScaledAlphaFold3Error(
                f"patched AlphaFold 3 source drifted at {relative}: "
                f"observed {actual_digest}, expected {expected_digest}"
            )
    return checkout


def _validated_file(value: object, *, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError(f"{label} must be a filesystem path")
    resolved = Path(value).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def _validated_python(value: object) -> Path:
    resolved = _validated_file(value, label="AlphaFold 3 Python")
    if not os.access(resolved, os.X_OK):
        raise PermissionError(f"AlphaFold 3 Python is not executable: {resolved}")
    return resolved


def _validated_model_dir(value: object) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("AlphaFold 3 model_dir must be a filesystem path")
    resolved = Path(value).resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"AlphaFold 3 model directory not found: {resolved}")
    if not any(
        child.is_file() and child.name.endswith((".bin", ".bin.zst"))
        for child in resolved.iterdir()
    ):
        raise FileNotFoundError(
            f"no official AlphaFold 3 parameter file found in {resolved}"
        )
    return resolved


def _prepare_output_dir(value: object) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("AlphaFold 3 output_dir must be a filesystem path")
    output_dir = Path(value).resolve()
    if output_dir.exists() and not output_dir.is_dir():
        raise PairScaledAlphaFold3Error(
            f"AlphaFold 3 output path is not a directory: {output_dir}"
        )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise PairScaledAlphaFold3Error(
            f"AlphaFold 3 output directory must be empty: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def build_pair_scaled_command(
    *,
    python_path: Path,
    alphafold3_root: Path,
    input_json_path: Path,
    output_dir: Path,
    model_dir: Path,
    num_recycles: int,
    num_diffusion_samples: int,
    beta: float,
) -> list[str]:
    """Build the fixed-argument official AF3 invocation without a shell."""

    return [
        str(python_path),
        str(alphafold3_root / "run_alphafold.py"),
        f"--json_path={input_json_path}",
        f"--output_dir={output_dir}",
        f"--model_dir={model_dir}",
        f"--num_recycles={num_recycles}",
        f"--num_diffusion_samples={num_diffusion_samples}",
        f"--pair_scaling_beta={beta}",
        "--norun_data_pipeline",
    ]


def _subprocess_environment(device: object) -> dict[str, str]:
    if not isinstance(device, str):
        raise ValueError("AlphaFold 3 device must be a string")
    environment = dict(os.environ)
    if device == "cuda":
        return environment
    if device.startswith("cuda:") and device[5:].isdigit():
        environment["CUDA_VISIBLE_DEVICES"] = device[5:]
        return environment
    raise ValueError("pair-scaled AlphaFold 3 requires device='cuda' or 'cuda:<index>'")


def _iter_numbers(value: object) -> Iterator[float]:
    if isinstance(value, bool):
        raise PairScaledAlphaFold3Error("confidence output unexpectedly contained a boolean")
    if isinstance(value, (int, float)):
        yield float(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_numbers(item)
        return
    raise PairScaledAlphaFold3Error(
        f"confidence output unexpectedly contained {type(value).__name__}"
    )


def _mean_numbers(value: object, *, label: str) -> float:
    numbers = list(_iter_numbers(value))
    if not numbers:
        raise PairScaledAlphaFold3Error(f"AlphaFold 3 {label} output is empty")
    return sum(numbers) / len(numbers)


def _extract_prediction(
    *,
    sample_index: int,
    cif_path: Path,
    summary_path: Path,
    full_path: Path,
    include_pae_matrix: bool,
) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text())
    full = json.loads(full_path.read_text())
    if not isinstance(summary, dict) or not isinstance(full, dict):
        raise PairScaledAlphaFold3Error("AlphaFold 3 confidence output is not an object")
    atom_plddts = full.get("atom_plddts")
    pae = full.get("pae")
    metrics: dict[str, Any] = {
        "avg_plddt": _mean_numbers(atom_plddts, label="atom_plddts"),
        "avg_pae": _mean_numbers(pae, label="pae"),
        "ptm": summary.get("ptm"),
        "iptm": summary.get("iptm"),
        "chain_pair_iptm": summary.get("chain_pair_iptm"),
        "ranking_score": summary.get("ranking_score"),
    }
    if include_pae_matrix:
        metrics["pae"] = pae
    return {
        "sample_index": sample_index,
        "structure_cif_output": cif_path.read_text(),
        "metrics": metrics,
    }


def _extract_predictions(
    output_dir: Path,
    *,
    model_seed: int,
    num_diffusion_samples: int,
    include_pae_matrix: bool,
) -> list[dict[str, Any]]:
    predictions: dict[int, dict[str, Any]] = {}
    prefix = f"seed-{model_seed}_sample-"
    for sample_dir in output_dir.rglob(f"{prefix}*"):
        if not sample_dir.is_dir() or not sample_dir.name.startswith(prefix):
            continue
        suffix = sample_dir.name[len(prefix) :]
        if not suffix.isdigit():
            continue
        sample_index = int(suffix)
        cif_path = sample_dir / "model.cif"
        summary_path = sample_dir / "summary_confidences.json"
        full_path = sample_dir / "confidences.json"
        if not all(path.is_file() for path in (cif_path, summary_path, full_path)):
            raise PairScaledAlphaFold3Error(
                f"AlphaFold 3 sample output is incomplete: {sample_dir}"
            )
        if sample_index in predictions:
            raise PairScaledAlphaFold3Error(
                f"duplicate AlphaFold 3 sample index {sample_index}"
            )
        predictions[sample_index] = _extract_prediction(
            sample_index=sample_index,
            cif_path=cif_path,
            summary_path=summary_path,
            full_path=full_path,
            include_pae_matrix=include_pae_matrix,
        )

    expected_indices = set(range(num_diffusion_samples))
    if set(predictions) != expected_indices:
        raise PairScaledAlphaFold3Error(
            "AlphaFold 3 returned the wrong diffusion-sample indices: "
            f"observed {sorted(predictions)}, expected {sorted(expected_indices)}"
        )
    return [predictions[index] for index in range(num_diffusion_samples)]


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _predict(input_dict: dict[str, Any]) -> dict[str, Any]:
    beta = validate_beta(input_dict.get("beta"))
    num_recycles = _positive_int(
        input_dict.get("num_recycles"), label="num_recycles"
    )
    num_diffusion_samples = _positive_int(
        input_dict.get("num_diffusion_samples"), label="num_diffusion_samples"
    )
    expected_count = expected_pair_scaling_invocations(num_recycles)
    checkout = verify_patched_checkout(
        input_dict.get("alphafold3_root", ""),
        input_dict.get("patch_path", ""),
    )
    python_path = _validated_python(input_dict.get("alphafold3_python_path"))
    input_json_path = _validated_file(
        input_dict.get("input_json_path"), label="AlphaFold 3 input JSON"
    )
    input_json = json.loads(input_json_path.read_text())
    if not isinstance(input_json, dict):
        raise ValueError("AlphaFold 3 input JSON must contain an object")
    model_seeds = input_json.get("modelSeeds")
    if (
        not isinstance(model_seeds, list)
        or len(model_seeds) != 1
        or isinstance(model_seeds[0], bool)
        or not isinstance(model_seeds[0], int)
    ):
        raise ValueError("pair-scaled AlphaFold 3 requires exactly one integer model seed")
    model_seed = model_seeds[0]
    if model_seed < 0:
        raise ValueError("pair-scaled AlphaFold 3 requires a non-negative model seed")

    output_dir = _prepare_output_dir(input_dict.get("output_dir"))
    model_dir = _validated_model_dir(input_dict.get("model_dir"))
    command = build_pair_scaled_command(
        python_path=python_path,
        alphafold3_root=checkout,
        input_json_path=input_json_path,
        output_dir=output_dir,
        model_dir=model_dir,
        num_recycles=num_recycles,
        num_diffusion_samples=num_diffusion_samples,
        beta=beta,
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=_subprocess_environment(input_dict.get("device")),
    )
    if bool(input_dict.get("verbose")):
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        stderr_tail = " | ".join(completed.stderr.strip().splitlines()[-20:])
        raise PairScaledAlphaFold3Error(
            f"pair-scaled AlphaFold 3 failed with exit {completed.returncode}: "
            f"{stderr_tail or '<no stderr>'}"
        )

    predictions = _extract_predictions(
        output_dir,
        model_seed=model_seed,
        num_diffusion_samples=num_diffusion_samples,
        include_pae_matrix=bool(input_dict.get("include_pae_matrix")),
    )
    result: dict[str, Any] = {"predictions": predictions}
    result["pair_scaling_audit"] = {
        "model": "alphafold3",
        "upstream_tag": AF3_UPSTREAM_TAG,
        "upstream_commit": AF3_UPSTREAM_COMMIT,
        "patch_sha256": PAIR_SCALING_PATCH_SHA256,
        "patched_source_sha256": dict(PATCHED_SOURCE_SHA256),
        "beta": beta,
        "scale_factor": 1.0 + beta,
        "model_seed": model_seed,
        "model_seed_count": 1,
        "expected_invocations_per_seed": expected_count,
        "observed_invocations_per_seed": expected_count,
        "expected_total_invocations": expected_count,
        "observed_total_invocations": expected_count,
        "count_verified_by": "patched_model_runner_host_assertion",
    }
    return result


def dispatch(input_dict: dict[str, Any]) -> dict[str, Any]:
    """ToolInstance-compatible worker entrypoint."""

    if input_dict.get("operation") != "predict_pair_scaled":
        raise ValueError(
            "pair-scaled AlphaFold 3 worker only accepts 'predict_pair_scaled'"
        )
    return _predict(input_dict)


def to_device(device: str) -> dict[str, Any]:
    """Report relocation success; each prediction is an isolated CLI process."""

    return {
        "success": True,
        "device": device,
        "note": "AlphaFold 3 runs in an isolated subprocess",
    }


def get_memory_stats() -> dict[str, Any]:
    """Return the expected telemetry shape for a subprocess-backed worker."""

    return {
        "available": False,
        "framework": "cli",
        "reason": "AlphaFold 3 runs in an isolated subprocess",
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise ValueError(
            "usage: python pair_scaled_alphafold3_inference.py "
            "<input_json_path> <output_json_path>"
        )
    request_path = Path(sys.argv[1])
    response_path = Path(sys.argv[2])
    request = json.loads(request_path.read_text())
    if not isinstance(request, dict):
        raise ValueError("worker request must contain a JSON object")
    response_path.write_text(json.dumps(dispatch(request)))
