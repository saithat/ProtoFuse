from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pytest

from protofuse.phillip.standalone import pair_scaled_alphafold3_inference as af3

PATCH_DIR = Path(af3.__file__).resolve().parents[1] / "patches"
PATCH_PATH = PATCH_DIR / "alphafold3_v3_0_1_pair_scaling.patch"
MANIFEST_PATH = PATCH_DIR / "alphafold3_v3_0_1_pair_scaling.json"


def _write_sample(root: Path, *, seed: int, sample_index: int) -> None:
    sample_dir = root / "job" / f"seed-{seed}_sample-{sample_index}"
    sample_dir.mkdir(parents=True)
    (sample_dir / "model.cif").write_text(f"sample {sample_index}")
    (sample_dir / "summary_confidences.json").write_text(
        json.dumps(
            {
                "ptm": 0.8,
                "iptm": 0.7,
                "chain_pair_iptm": [[0.8]],
                "ranking_score": 0.9 - sample_index / 100,
            }
        )
    )
    (sample_dir / "confidences.json").write_text(
        json.dumps({"atom_plddts": [80.0, 100.0], "pae": [[1.0, 3.0]]})
    )


def _fake_patched_checkout(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    contents = {
        "run_alphafold.py": "patched runner\n",
        "src/alphafold3/model/model.py": "patched model\n",
        "src/alphafold3/model/network/evoformer.py": "patched evoformer\n",
    }
    digests: dict[str, str] = {}
    for relative, content in contents.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        digests[relative] = hashlib.sha256(content.encode()).hexdigest()
    monkeypatch.setattr(af3, "PATCHED_SOURCE_SHA256", digests)
    return digests


@pytest.mark.parametrize("beta", af3.ALLOWED_PAIR_SCALING_BETAS)
def test_beta_allowlist_accepts_and_canonicalizes(beta: float) -> None:
    assert af3.validate_beta(beta + 1e-13) == beta


@pytest.mark.parametrize("beta", [math.nan, math.inf, -math.inf, 0.01, True, "0.0"])
def test_beta_validation_rejects_nonfinite_or_off_grid(beta: object) -> None:
    with pytest.raises(ValueError):
        af3.validate_beta(beta)


def test_beta_zero_is_an_object_identity_operation() -> None:
    marker = object()

    assert af3.scale_pairformer_input_for_audit(marker, 0.0) is marker
    assert af3.scale_pairformer_input_for_audit(4.0, -0.15) == 3.4


def test_recycle_count_includes_initial_trunk_pass() -> None:
    assert af3.expected_pair_scaling_invocations(0) == 1
    assert af3.expected_pair_scaling_invocations(1) == 2
    assert af3.expected_pair_scaling_invocations(3) == 4
    with pytest.raises(ValueError):
        af3.expected_pair_scaling_invocations(-1)
    with pytest.raises(ValueError):
        af3.expected_pair_scaling_invocations(True)


def test_patch_and_manifest_are_pinned_to_official_v301() -> None:
    assert af3.verify_patch_artifact(PATCH_PATH) == PATCH_PATH.resolve()
    manifest = json.loads(MANIFEST_PATH.read_text())

    assert manifest["upstream_commit"] == af3.AF3_UPSTREAM_COMMIT
    assert manifest["upstream_tag"] == af3.AF3_UPSTREAM_TAG
    assert manifest["patch_sha256"] == af3.PAIR_SCALING_PATCH_SHA256
    assert manifest["patched_source_sha256"] == af3.PATCHED_SOURCE_SHA256

    patch_text = PATCH_PATH.read_text()
    assert "diff --git a/src/alphafold3/model/network/confidence_head.py" not in patch_text
    assert patch_text.index("del key  # Unused after this point.") < patch_text.index(
        "+      pair_activations = _scale_pairformer_input"
    )
    assert patch_text.index(
        "+      pair_activations = _scale_pairformer_input"
    ) < patch_text.index("single_activations = hm.Linear")
    assert "+  if beta == 0.0:\n+    return pair_activations" in patch_text


def test_checkout_verification_detects_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "alphafold3"
    _fake_patched_checkout(checkout, monkeypatch)

    assert af3.verify_patched_checkout(checkout, PATCH_PATH) == checkout.resolve()

    (checkout / "run_alphafold.py").write_text("drifted\n")
    with pytest.raises(af3.PairScaledAlphaFold3Error, match="source drifted"):
        af3.verify_patched_checkout(checkout, PATCH_PATH)


def test_command_uses_explicit_interpreter_and_pair_scaling_flag(tmp_path: Path) -> None:
    command = af3.build_pair_scaled_command(
        python_path=tmp_path / "venv" / "bin" / "python",
        alphafold3_root=tmp_path / "alphafold3",
        input_json_path=tmp_path / "input.json",
        output_dir=tmp_path / "output",
        model_dir=tmp_path / "models",
        num_recycles=3,
        num_diffusion_samples=5,
        beta=-0.15,
    )

    assert command[0].endswith("venv/bin/python")
    assert command[1].endswith("alphafold3/run_alphafold.py")
    assert "--pair_scaling_beta=-0.15" in command
    assert "--num_recycles=3" in command
    assert "--num_diffusion_samples=5" in command
    assert "--norun_data_pipeline" in command


def test_extract_predictions_returns_every_sample_in_index_order(tmp_path: Path) -> None:
    for sample_index in (4, 1, 3, 0, 2):
        _write_sample(tmp_path, seed=7, sample_index=sample_index)

    predictions = af3._extract_predictions(  # noqa: SLF001 - focused worker audit
        tmp_path,
        model_seed=7,
        num_diffusion_samples=5,
        include_pae_matrix=True,
    )

    assert [prediction["sample_index"] for prediction in predictions] == list(range(5))
    assert [prediction["structure_cif_output"] for prediction in predictions] == [
        f"sample {index}" for index in range(5)
    ]
    assert predictions[0]["metrics"]["avg_plddt"] == 90.0
    assert predictions[0]["metrics"]["avg_pae"] == 2.0
    assert predictions[0]["metrics"]["pae"] == [[1.0, 3.0]]


def test_extract_predictions_fails_on_missing_sample(tmp_path: Path) -> None:
    _write_sample(tmp_path, seed=7, sample_index=0)

    with pytest.raises(af3.PairScaledAlphaFold3Error, match="wrong diffusion-sample"):
        af3._extract_predictions(  # noqa: SLF001 - focused worker audit
            tmp_path,
            model_seed=7,
            num_diffusion_samples=2,
            include_pae_matrix=False,
        )


def test_predict_returns_samples_and_verified_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tmp_path / "alphafold3"
    digests = _fake_patched_checkout(checkout, monkeypatch)
    python_path = tmp_path / "af3_venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("interpreter marker")
    python_path.chmod(0o755)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "af3.bin.zst").write_bytes(b"parameters marker")
    input_json_path = tmp_path / "input.json"
    input_json_path.write_text(json.dumps({"name": "job", "modelSeeds": [11]}))
    output_dir = tmp_path / "output"
    seen_command: list[str] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen_command.extend(command)
        for sample_index in range(2):
            _write_sample(output_dir, seed=11, sample_index=sample_index)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(af3.subprocess, "run", fake_run)
    result = af3.dispatch(
        {
            "operation": "predict_pair_scaled",
            "alphafold3_root": str(checkout),
            "patch_path": str(PATCH_PATH),
            "alphafold3_python_path": str(python_path),
            "input_json_path": str(input_json_path),
            "output_dir": str(output_dir),
            "model_dir": str(model_dir),
            "device": "cuda:0",
            "verbose": False,
            "include_pae_matrix": False,
            "num_recycles": 3,
            "num_diffusion_samples": 2,
            "beta": -0.15,
        }
    )

    assert [item["sample_index"] for item in result["predictions"]] == [0, 1]
    audit = result["pair_scaling_audit"]
    assert audit["patched_source_sha256"] == digests
    assert audit["expected_invocations_per_seed"] == 4
    assert audit["observed_invocations_per_seed"] == 4
    assert audit["count_verified_by"] == "patched_model_runner_host_assertion"
    assert "--pair_scaling_beta=-0.15" in seen_command


def test_dispatch_rejects_other_operations() -> None:
    with pytest.raises(ValueError, match="only accepts"):
        af3.dispatch({"operation": "predict"})
