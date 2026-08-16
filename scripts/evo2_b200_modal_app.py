"""Upstream-aligned B200 Modal service for the reviewed Evo2 7B workload."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

import modal
from proto_tools.modal.app import HF_TOKEN_SECRET, MODEL_CACHE, NO_RETRIES, get_app
from proto_tools.modal.base_images import with_proto_tools
from proto_tools.modal.manifest import SERVICE_MODAL_TIMEOUTS
from proto_tools.modal.registry import register_tools
from proto_tools.modal.utils import RUNTIME_ENV, ensure_gpu_ready, env_for, run_tool_call

APP_NAME = "proto-tools-evo2"
SERVICE_NAME = "Evo2Service"
GPU = "B200:1"
ARC_BASE_IMAGE = "nvcr.io/nvidia/pytorch:25.04-py3"
OVERRIDES_DIR = Path(__file__).with_name("evo2_b200")


def _runtime_versions() -> dict[str, Any]:
    import torch  # type: ignore[import-not-found]

    return {
        "gpu": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "torch": str(torch.__version__),
        "torch_cuda": str(torch.version.cuda),
        "transformer_engine": importlib.metadata.version("transformer-engine"),
        "flash_attn": importlib.metadata.version("flash-attn"),
        "evo2": importlib.metadata.version("evo2"),
        "vtx": importlib.metadata.version("vtx"),
    }


def _warmup() -> None:
    """Build the isolated worker, verify SM100 support, and warm the reviewed checkpoint."""
    import torch
    from proto_tools.tools.causal_models.evo2.evo2_sample import (
        Evo2SampleConfig,
        example_input,
        run_evo2_sample,
    )

    capability = torch.cuda.get_device_capability(0)
    if capability < (10, 0):
        raise RuntimeError(f"Evo2 B200 image expected SM100+, found {capability}")
    print(_runtime_versions())
    result = run_evo2_sample(
        example_input(),
        Evo2SampleConfig(
            batch_size=1,
            max_new_tokens=8,
            prepend_prompt=False,
            seed=0,
            stop_at_eos=False,
            top_k=1,
        ),
    )
    if not result.results or len(result.results[0].sequence) != 8:
        raise RuntimeError("Evo2 B200 warmup did not return the requested continuation")


# Arc's own Evo2 Dockerfile uses this NVIDIA image. The tool worker reuses its
# Blackwell-built CUDA/PyTorch/TransformerEngine/FlashAttention stack through a
# narrow PYTHONPATH override rather than reinstalling the old cu124 stack.
try:
    proto_tools_requirements = tuple(
        requirement
        for requirement in (importlib.metadata.requires("proto-tools") or ())
        if "extra ==" not in requirement
    )
except importlib.metadata.PackageNotFoundError:
    # The deployed function re-imports this source after proto-tools has been
    # copied in without distribution metadata. Its image is already built; the
    # dependency list is needed only while defining that image locally.
    proto_tools_requirements = ()
base = modal.Image.from_registry(
    ARC_BASE_IMAGE,
    # Modal installs its own runtime immediately after FROM, before ordinary
    # image layers run. NVIDIA's pip constraint must therefore be cleared in
    # this base-setup phase, or those two runtimes conflict on aiohttp.
    setup_dockerfile_commands=["RUN truncate -s 0 /etc/pip/constraint.txt"],
)
base = base.pip_install(
    *proto_tools_requirements,
    env={"PIP_CONSTRAINT": ""},
)
base = base.pip_install(
    "flash-attn==2.8.0.post2",
    extra_options="--no-build-isolation",
    env={"PIP_CONSTRAINT": ""},
)
base = base.pip_install(
    "evo2==0.5.5",
    "vtx==1.1.0",
    "huggingface-hub",
    "einops==0.8.1",
    "rich",
    extra_options="--no-deps",
    env={"PIP_CONSTRAINT": ""},
)
image = with_proto_tools(base, overrides="evo2", overrides_dir=OVERRIDES_DIR)
image = (
    image.env(env_for())
    .run_function(
        _warmup,
        gpu=GPU,
        volumes={"/weights": MODEL_CACHE},
        secrets=[HF_TOKEN_SECRET],
        include_source=True,
        timeout=3600,
    )
    .env(RUNTIME_ENV)
)

app = get_app(APP_NAME)


@app.function(image=image, gpu=GPU, volumes={"/weights": MODEL_CACHE}, timeout=300)
def runtime_provenance() -> dict[str, Any]:
    """Return the exact deployed runtime and accelerator versions."""
    ensure_gpu_ready("evo2-b200-provenance")
    return _runtime_versions()


@app.cls(
    include_source=True,
    image=image,
    gpu=GPU,
    max_containers=1,
    scaledown_window=3600,
    volumes={"/weights": MODEL_CACHE},
    timeout=SERVICE_MODAL_TIMEOUTS[SERVICE_NAME],
    retries=NO_RETRIES,
    secrets=[HF_TOKEN_SECRET],
)
@register_tools({"evo2-sample": "sample", "evo2-score": "score"})
class Evo2Service:
    """Proto-tools-compatible Evo2 service using Arc's current B200-capable base."""

    @modal.enter()
    def setup(self) -> None:
        ensure_gpu_ready("evo2")
        from proto_tools.utils.tool_instance import ToolInstance

        self._persist_ctx = ToolInstance.persist_tool("evo2")
        self.instance = self._persist_ctx.__enter__()

    @modal.exit()
    def teardown(self) -> None:
        self._persist_ctx.__exit__(None, None, None)

    @modal.method()
    def sample(self, input_dict: dict[str, Any], config_dict: dict[str, Any]) -> dict[str, Any]:
        from proto_tools.tools.causal_models.evo2.evo2_sample import (
            Evo2SampleConfig,
            Evo2SampleInput,
            run_evo2_sample,
        )

        return run_tool_call(
            run_evo2_sample,
            Evo2SampleInput,
            Evo2SampleConfig,
            input_dict,
            config_dict,
            instance=self.instance,
        )

    @modal.method()
    def score(self, input_dict: dict[str, Any], config_dict: dict[str, Any]) -> dict[str, Any]:
        from proto_tools.tools.causal_models.evo2.evo2_score import (
            Evo2ScoringConfig,
            Evo2ScoringInput,
            run_evo2_score,
        )

        return run_tool_call(
            run_evo2_score,
            Evo2ScoringInput,
            Evo2ScoringConfig,
            input_dict,
            config_dict,
            instance=self.instance,
        )

    @modal.method()
    def release(self, kv_caches: Any) -> dict[str, Any]:
        """Release cache handles on the same persistent Evo2 worker."""
        from proto_tools.utils.tool_instance import ToolInstance

        return ToolInstance.dispatch(
            "evo2",
            {"operation": "release_kv_caches", "kv_caches": kv_caches},
            instance=self.instance,
        )
