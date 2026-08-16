"""Modal deployment for the reviewed pair-scaled Boltz-2 backend."""

from __future__ import annotations

from typing import Any

import modal
from proto_tools.modal.app import (
    HF_TOKEN_SECRET,
    MODEL_CACHE,
    SCALEDOWN_WINDOW,
    SERVICE_RETRIES,
    get_app,
)
from proto_tools.modal.gpu_profiles import GPU_DEFAULT
from proto_tools.modal.structure_prediction.boltz2_deployment.boltz2_service import (
    image as boltz2_image,
)
from proto_tools.modal.utils import ensure_gpu_ready

from protofuse.phillip.pair_scaling_boltz2 import (
    PAIR_SCALING_MODAL_APP,
    run_prepared_pair_scaled_boltz2,
)

image = boltz2_image.add_local_python_source("protofuse", copy=True)
app = get_app(PAIR_SCALING_MODAL_APP)


@app.cls(
    include_source=False,
    image=image,
    gpu=GPU_DEFAULT,
    scaledown_window=SCALEDOWN_WINDOW,
    volumes={"/weights": MODEL_CACHE},
    timeout=3600,
    retries=SERVICE_RETRIES,
    secrets=[HF_TOKEN_SECRET],
)
class PairScalingBoltz2Service:
    """GPU service that exposes only the audited pair-scaled prediction path."""

    @modal.enter()
    def setup(self) -> None:
        ensure_gpu_ready("boltz2-pair-scaled")
        from proto_tools.utils.tool_instance import ToolInstance

        self._persist_ctx = ToolInstance.persist_tool("boltz2")
        self.instance = self._persist_ctx.__enter__()

    @modal.exit()
    def teardown(self) -> None:
        self._persist_ctx.__exit__(None, None, None)

    @modal.method()
    def predict(
        self,
        input_dict: dict[str, Any],
        config_dict: dict[str, Any],
        beta: float,
    ) -> list[dict[str, Any]]:
        from proto_tools.tools.structure_prediction.boltz2 import Boltz2Config, Boltz2Input

        inputs = Boltz2Input.model_validate(input_dict)
        config = Boltz2Config.model_validate(config_dict)
        structures = run_prepared_pair_scaled_boltz2(
            inputs,
            config,
            beta=beta,
            instance=self.instance,
        )
        return [structure.model_dump(mode="json") for structure in structures]
