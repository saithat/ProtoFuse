from __future__ import annotations

from typing import Any

import pytest
from proto_tools import Structure

from protofuse.phillip.pair_scaling_boltz2 import (
    PAIR_SCALING_EXECUTION_ENV,
    boltz2_pair_scaling_backend,
)
from protofuse.phillip.pair_scaling_contract import PairScalingBackendRequest
from protofuse.sai.hardware import experiment_hardware, pinned_modal_hardware

_MINIMAL_PDB = """\
ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 50.00           C
END
"""


def test_modal_hardware_must_be_explicit_and_supported() -> None:
    with pytest.raises(ValueError, match="requires modal_gpu"):
        experiment_hardware("modal", None)
    with pytest.raises(ValueError, match="only valid"):
        experiment_hardware(None, "H200:1")


def test_pinned_modal_hardware_overrides_one_isolated_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modal
    from proto_tools.modal import client as modal_client

    options: dict[str, Any] = {}

    class FakeService:
        def with_options(self, **kwargs: Any) -> FakeService:
            options.update(kwargs)
            return self

        def hydrate(self) -> None:
            options["hydrated"] = True

        def __call__(self) -> FakeService:
            return self

        def sample(self) -> None:
            return None

    def fake_from_name(*args: Any, **kwargs: Any) -> FakeService:
        options["lookup"] = (args, kwargs)
        return FakeService()

    original_bound_method = modal_client._bound_method
    monkeypatch.setattr(modal.Cls, "from_name", staticmethod(fake_from_name))
    hardware = experiment_hardware("modal", "H200:1", context_id="paired-test")

    with pinned_modal_hardware(hardware):
        method = modal_client._bound_method("app", "Service", "sample", "tool")

    assert method() is None
    assert modal_client._bound_method is original_bound_method
    assert options["lookup"] == (
        ("app", "Service"),
        {"environment_name": None, "client": None},
    )
    assert options["hydrated"] is True
    assert options == {
        "lookup": (
            ("app", "Service"),
            {"environment_name": None, "client": None},
        ),
        "gpu": "H200:1",
        "env": {
            "PROTOFUSE_HARDWARE_CONTEXT": "paired-test",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        },
        "max_containers": 1,
        "retries": 0,
        "scaledown_window": 3600,
        "hydrated": True,
    }


def test_pair_scaled_boltz_uses_the_pinned_modal_option_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modal

    options: dict[str, Any] = {}

    class FakeRemoteMethod:
        def remote(self, *args: Any) -> list[dict[str, Any]]:
            options["remote_args"] = args
            return [
                Structure(
                    structure=_MINIMAL_PDB,
                    source="boltz2-pair-scaled",
                ).model_dump(mode="json")
            ]

    class FakeService:
        predict = FakeRemoteMethod()

        def with_options(self, **kwargs: Any) -> FakeService:
            options.update(kwargs)
            return self

        def hydrate(self) -> None:
            options["hydrated"] = True

        def __call__(self) -> FakeService:
            return self

    def fake_from_name(*args: Any, **kwargs: Any) -> FakeService:
        options["lookup"] = (args, kwargs)
        return FakeService()

    monkeypatch.setattr(modal.Cls, "from_name", staticmethod(fake_from_name))
    monkeypatch.delenv(PAIR_SCALING_EXECUTION_ENV, raising=False)
    monkeypatch.setenv("MODAL_ENVIRONMENT", "pair-test-env")
    request = PairScalingBackendRequest(
        model="boltz2",
        beta=-0.15,
        model_seed=0,
        recycling_steps=3,
        sampling_steps=200,
        diffusion_samples=1,
        step_scale=1.5,
        use_msa=False,
        max_msa_seqs=128,
        subsample_msa=False,
    )
    hardware = experiment_hardware("modal", "H200:1", context_id="pair-test")

    with pinned_modal_hardware(hardware):
        structures = boltz2_pair_scaling_backend(["AAAA"], request)

    assert len(structures) == 1
    assert structures[0].source == "boltz2-pair-scaled"
    assert options["lookup"] == (
        ("protofuse-pair-scaling", "PairScalingBoltz2Service"),
        {"environment_name": "pair-test-env", "client": None},
    )
    assert options["gpu"] == "H200:1"
    assert options["max_containers"] == 1
    assert options["retries"] == 0
    assert options["scaledown_window"] == 3600
    assert options["env"] == {
        "PROTOFUSE_HARDWARE_CONTEXT": "pair-test",
        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
    }
    input_payload, config_payload, beta = options["remote_args"]
    assert len(input_payload["complexes"]) == 1
    assert config_payload["device"] == "cuda"
    assert config_payload["seed"] == 0
    assert beta == -0.15
