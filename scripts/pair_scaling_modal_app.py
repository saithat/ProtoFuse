"""Private Modal service for ProtoFuse's required pair-scaled Boltz 2 backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import modal
from proto_tools.entities.structures import BFactorType, Structure
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
from proto_tools.tools.structure_prediction.boltz2 import Boltz2Config, Boltz2Input
from proto_tools.tools.structure_prediction.boltz2 import boltz2 as boltz2_module
from proto_tools.tools.structure_prediction.boltz2.boltz2 import Boltz2Metrics
from proto_tools.tools.structure_prediction.boltz2.helpers import (
    build_chain_msa_paths,
    complex_to_yaml,
)
from proto_tools.tools.structure_prediction.shared_data_models import (
    normalize_output_chain_ids,
)
from proto_tools.utils.tool_instance import ToolInstance

APP_NAME = "protofuse-pair-scaling"
SERVICE_NAME = "PairScalingBoltz2Service"
CONTAINER_STANDALONE = "/root/pair_scaled_boltz2_inference.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_STANDALONE = (
    REPOSITORY_ROOT
    / "src"
    / "protofuse"
    / "phillip"
    / "standalone"
    / "pair_scaled_boltz2_inference.py"
)

image = boltz2_image.add_local_file(
    __file__,
    "/root/pair_scaling_modal_app.py",
    copy=True,
)
image = image.add_local_file(
    LOCAL_STANDALONE,
    CONTAINER_STANDALONE,
    copy=True,
)

app = get_app(APP_NAME)


def _metrics_from_output(output_data: dict[str, Any]) -> Boltz2Metrics:
    formatted = output_data["metrics"]
    metrics: dict[str, Any] = {
        "confidence_score": float(formatted["confidence_score"]),
        "ptm": float(formatted["ptm"]),
        "iptm": float(formatted["iptm"]),
        "chains_ptm": formatted["chains_ptm"],
        "pair_chains_iptm": formatted["pair_chains_iptm"],
        "avg_pae": float(formatted["avg_pae"]),
        "pae": formatted["pae"],
    }
    for name in (
        "ligand_iptm",
        "protein_iptm",
        "complex_plddt",
        "complex_iplddt",
        "complex_pde",
        "complex_ipde",
    ):
        if name in formatted:
            metrics[name] = float(formatted[name])
    return Boltz2Metrics(**metrics)


def _predict_prepared(
    inputs: Boltz2Input,
    config: Boltz2Config,
    beta: float,
    instance: ToolInstance,
) -> list[Structure]:
    structures: list[Structure] = []
    base_seed = config.seed if config.seed is not None else config.get_random_int()
    base_inference = Path(boltz2_module.__file__).with_name("standalone") / "inference.py"
    for index, sp_complex in enumerate(inputs.complexes):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "boltz2_output"
            output_dir.mkdir()
            chain_msa_paths = None
            if inputs.msas is not None:
                chain_msa_paths = build_chain_msa_paths(
                    sp_complex,
                    inputs.msas[index],
                    temp_dir,
                    verbose=config.verbose,
                )
            input_path = Path(temp_dir) / "boltz2_input.yaml"
            input_path.write_text(
                complex_to_yaml(sp_complex.chains, chain_msa_paths=chain_msa_paths)
            )
            output_data = ToolInstance.dispatch(
                "boltz2",
                {
                    "operation": "predict_pair_scaled",
                    "input_yaml_path": str(input_path),
                    "output_dir": str(output_dir),
                    "base_inference_path": str(base_inference),
                    "beta": beta,
                    "recycling_steps": config.recycling_steps,
                    "sampling_steps": config.sampling_steps,
                    "diffusion_samples": config.diffusion_samples,
                    "step_scale": config.step_scale,
                    "max_msa_seqs": config.max_msa_seqs,
                    "subsample_msa": config.subsample_msa,
                    "num_workers": config.num_workers,
                    "device": config.device,
                    "verbose": config.verbose,
                    "seed": base_seed + index,
                    "include_pae_matrix": config.include_pae_matrix,
                },
                instance=instance,
                script_path=Path(CONTAINER_STANDALONE),
                config=config,
            )
            audit = output_data.get("pair_scaling_audit")
            if not isinstance(audit, dict) or audit.get("beta") != beta:
                raise RuntimeError("Boltz pair-scaling worker returned no matching audit record")
            predictions = output_data.get("predictions")
            if not isinstance(predictions, list) or len(predictions) != config.diffusion_samples:
                raise RuntimeError(
                    "Boltz pair-scaling worker did not return every requested "
                    f"diffusion sample: expected {config.diffusion_samples}"
                )
            for prediction in predictions:
                if not isinstance(prediction, dict):
                    raise RuntimeError("Boltz pair-scaling worker returned an invalid prediction")
                structure = Structure(
                    structure=prediction["structure_cif_output"],
                    b_factor_type=BFactorType.PLDDT,
                    metrics=_metrics_from_output(prediction),
                    source="boltz2-pair-scaled",
                )
                structures.append(normalize_output_chain_ids(structure, sp_complex.chains))
    return structures


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
    """GPU service exposing only the audited pair-scaled prediction path."""

    @modal.enter()
    def setup(self) -> None:
        ensure_gpu_ready("boltz2-pair-scaled")
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
        inputs = Boltz2Input.model_validate(input_dict)
        config = Boltz2Config.model_validate(config_dict)
        structures = _predict_prepared(inputs, config, beta, self.instance)
        return [structure.model_dump(mode="json") for structure in structures]
