from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from proto_tools.tools.structure_prediction.boltz2 import Boltz2Config

from protofuse.phillip.pair_scaling_alphafold3 import (
    _af3_config,
)
from protofuse.phillip.pair_scaling_alphafold3 import (
    _prepare_inputs as _prepare_af3_inputs,
)
from protofuse.phillip.pair_scaling_boltz2 import _prepare_inputs
from protofuse.phillip.pair_scaling_contract import PairScalingBackendRequest
from protofuse.phillip.pair_scaling_msa import AF3_SERVER_MSA_ENV
from protofuse.phillip.standalone.pair_scaled_boltz2_inference import (
    _extract_diffusion_samples,
    _scaled_pairformer_inputs,
)


class _Scalable:
    def __init__(self, value: float) -> None:
        self.value = value

    def __mul__(self, factor: float) -> _Scalable:
        return _Scalable(self.value * factor)


def test_pairformer_hook_scales_only_positional_z() -> None:
    audit: dict[str, Any] = {"invocations": 0}
    args, kwargs = _scaled_pairformer_inputs(
        ("sequence", _Scalable(4.0)),
        {"mask": "unchanged"},
        beta=-0.25,
        audit=audit,
    )

    assert args[0] == "sequence"
    assert isinstance(args[1], _Scalable)
    assert args[1].value == 3.0
    assert kwargs == {"mask": "unchanged"}
    assert audit["invocations"] == 1


def test_pairformer_hook_scales_keyword_z() -> None:
    audit: dict[str, Any] = {"invocations": 0}
    args, kwargs = _scaled_pairformer_inputs(
        (),
        {"s": "sequence", "z": _Scalable(2.0)},
        beta=0.5,
        audit=audit,
    )

    assert args == ()
    assert kwargs["s"] == "sequence"
    assert isinstance(kwargs["z"], _Scalable)
    assert kwargs["z"].value == 3.0
    assert audit["invocations"] == 1


def test_fixed_sequence_batch_maps_to_one_seeded_diffusion_batch() -> None:
    inputs, _ = _prepare_inputs(
        ["AAAA", "AAAA", "AAAA"],
        Boltz2Config(use_msa=False, diffusion_samples=3),
    )

    assert len(inputs.complexes) == 1
    assert inputs.complexes[0].chains[0].sequence == "AAAA"


def test_boltz_msa_mode_reuses_exact_server_alignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AF3_SERVER_MSA_ENV, raising=False)

    with pytest.raises(RuntimeError, match="refuses to substitute"):
        _prepare_inputs(
            ["AAAA"],
            Boltz2Config(use_msa=True, diffusion_samples=1),
        )


@pytest.mark.parametrize(
    "sequences",
    [
        ["AAAA", "BBBB"],
        ["AAAA"],
    ],
)
def test_fixed_sequence_batch_rejects_wrong_draw_contract(sequences: list[str]) -> None:
    with pytest.raises(ValueError, match="same fixed sequence|proposal count"):
        _prepare_inputs(
            sequences,
            Boltz2Config(use_msa=False, diffusion_samples=2),
        )


def test_boltz_worker_returns_every_diffusion_sample(tmp_path: Path) -> None:
    input_path = tmp_path / "request.yaml"
    prediction_dir = (
        tmp_path / "output" / "boltz_results_request" / "predictions" / "request"
    )
    prediction_dir.mkdir(parents=True)
    input_path.write_text("version: 1\n")
    for index in range(2):
        (prediction_dir / f"confidence_request_model_{index}.json").write_text(
            json.dumps({"confidence_score": index / 10})
        )
        (prediction_dir / f"request_model_{index}.cif").write_text(
            f"data_sample_{index}\n"
        )
        np.savez(
            prediction_dir / f"pae_request_model_{index}.npz",
            pae=np.asarray([[float(index)]], dtype=np.float32),
        )

    outputs = _extract_diffusion_samples(
        str(tmp_path / "output"),
        str(input_path),
        diffusion_samples=2,
        include_pae_matrix=False,
    )

    assert [item["sample_index"] for item in outputs] == [0, 1]
    assert [item["structure_cif_output"] for item in outputs] == [
        "data_sample_0\n",
        "data_sample_1\n",
    ]
    assert [item["metrics"]["avg_pae"] for item in outputs] == [0.0, 1.0]


def _af3_request(*, use_msa: bool, diffusion_samples: int) -> PairScalingBackendRequest:
    return PairScalingBackendRequest(
        model="alphafold3",
        beta=-0.15,
        model_seed=2,
        recycling_steps=3,
        sampling_steps=200,
        diffusion_samples=diffusion_samples,
        step_scale=1.5,
        use_msa=use_msa,
        max_msa_seqs=1024,
        subsample_msa=False,
    )


def test_af3_query_only_batch_maps_to_one_seeded_diffusion_batch() -> None:
    config = _af3_config(_af3_request(use_msa=False, diffusion_samples=2))
    inputs = _prepare_af3_inputs(["AAAA", "AAAA"], config)

    assert config.seed == 2
    assert config.num_recycles == 3
    assert config.num_diffusion_samples == 2
    assert len(inputs.complexes) == 1
    assert inputs.msas is None


def test_af3_msa_mode_requires_exact_user_held_server_alignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AF3_SERVER_MSA_ENV, raising=False)
    config = _af3_config(_af3_request(use_msa=True, diffusion_samples=1))

    with pytest.raises(RuntimeError, match="refuses to substitute"):
        _prepare_af3_inputs(["AAAA"], config)


def test_af3_msa_query_row_must_match_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    msa_path = tmp_path / "server.a3m"
    msa_path.write_text(">query\nBBBB\n>homolog\nBB-B\n")
    monkeypatch.setenv(AF3_SERVER_MSA_ENV, str(msa_path))
    config = _af3_config(_af3_request(use_msa=True, diffusion_samples=1))

    with pytest.raises(ValueError, match="query row"):
        _prepare_af3_inputs(["AAAA"], config)
