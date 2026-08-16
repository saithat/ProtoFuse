"""Reviewed Boltz-2 backend for pair-representation scaling."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from proto_tools.entities.structures import BFactorType, Structure
from proto_tools.tools.structure_prediction.boltz2 import (
    Boltz2Config,
    Boltz2Input,
)
from proto_tools.tools.structure_prediction.boltz2 import boltz2 as boltz2_module
from proto_tools.tools.structure_prediction.boltz2.boltz2 import Boltz2Metrics
from proto_tools.tools.structure_prediction.boltz2.helpers import (
    build_chain_msa_paths,
    complex_to_yaml,
)
from proto_tools.tools.structure_prediction.shared_data_models import (
    Chain,
    Complex,
    normalize_output_chain_ids,
)
from proto_tools.utils.tool_instance import ToolInstance

from protofuse.phillip.pair_scaling_msa import load_paper_server_msa
from protofuse.phillip.pair_scaling_values import validate_paper_beta

PAIR_SCALING_MODAL_APP = "protofuse-pair-scaling"
PAIR_SCALING_MODAL_CLASS = "PairScalingBoltz2Service"
PAIR_SCALING_MODAL_TOOL_KEY = "pair-scaled-boltz2"
PAIR_SCALING_EXECUTION_ENV = "PROTOFUSE_PAIR_SCALING_EXECUTION"

_STANDALONE_PATH = (
    Path(__file__).with_name("standalone") / "pair_scaled_boltz2_inference.py"
)
_BASE_INFERENCE_PATH = (
    Path(boltz2_module.__file__).with_name("standalone") / "inference.py"
)


def _boltz_config(request: Any) -> Boltz2Config:
    validate_paper_beta(request.beta)
    return Boltz2Config(
        recycling_steps=request.recycling_steps,
        sampling_steps=request.sampling_steps,
        diffusion_samples=request.diffusion_samples,
        step_scale=request.step_scale,
        use_msa=request.use_msa,
        max_msa_seqs=request.max_msa_seqs,
        subsample_msa=request.subsample_msa,
        seed=request.model_seed,
        device="cuda",
    )


def _prepare_inputs(
    sequences: list[str],
    config: Boltz2Config,
) -> tuple[Boltz2Input, Boltz2Config]:
    if not sequences:
        raise ValueError("pair-scaling requires at least one fixed-sequence draw")
    if len(set(sequences)) != 1:
        raise ValueError(
            "pair-scaling diffusion draws must all use the same fixed sequence"
        )
    if len(sequences) != config.diffusion_samples:
        raise ValueError(
            "pair-scaling proposal count must equal diffusion_samples so every "
            "paper draw comes from one seeded diffusion batch"
        )
    complexes = [
        Complex(chains=[Chain(sequence=sequences[0], entity_type="protein")])
    ]
    msas = [load_paper_server_msa(sequences[0])] if config.use_msa else None
    inputs = Boltz2Input(complexes=complexes, msas=msas)
    prepared = config.preprocess(inputs)
    if isinstance(prepared, tuple):
        prepared_inputs, prepared_config = prepared
        return Boltz2Input.model_validate(prepared_inputs), Boltz2Config.model_validate(
            prepared_config
        )
    return Boltz2Input.model_validate(prepared), config


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
    optional = (
        "ligand_iptm",
        "protein_iptm",
        "complex_plddt",
        "complex_iplddt",
        "complex_pde",
        "complex_ipde",
    )
    for name in optional:
        if name in formatted:
            metrics[name] = float(formatted[name])
    return Boltz2Metrics(**metrics)


def run_prepared_pair_scaled_boltz2(
    inputs: Boltz2Input,
    config: Boltz2Config,
    *,
    beta: float,
    instance: ToolInstance | None = None,
) -> list[Structure]:
    """Run one fixed sequence and return every audited diffusion sample."""

    if len(inputs.complexes) != 1:
        raise ValueError("pair-scaled Boltz expects one fixed-sequence complex")
    structures: list[Structure] = []
    base_seed = config.seed if config.seed is not None else config.get_random_int()
    for sp_complex in inputs.complexes:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "boltz2_output"
            output_dir.mkdir()
            chain_msa_paths = None
            if inputs.msas is not None:
                chain_msa_paths = build_chain_msa_paths(
                    sp_complex,
                    inputs.msas[0],
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
                    "base_inference_path": str(_BASE_INFERENCE_PATH),
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
                    "seed": base_seed,
                    "include_pae_matrix": config.include_pae_matrix,
                },
                instance=instance,
                script_path=_STANDALONE_PATH,
                config=config,
            )
            audit = output_data.get("pair_scaling_audit")
            if not isinstance(audit, dict) or audit.get("beta") != beta:
                raise RuntimeError("Boltz pair-scaling worker returned no matching audit record")
            predictions = output_data.get("predictions")
            if not isinstance(predictions, list) or len(predictions) != config.diffusion_samples:
                raise RuntimeError(
                    "Boltz pair-scaling worker did not return every requested diffusion sample"
                )
            for sample_index, output in enumerate(predictions):
                if not isinstance(output, dict) or output.get("sample_index") != sample_index:
                    raise RuntimeError("Boltz pair-scaling sample ordering audit failed")
                structure = Structure(
                    structure=output["structure_cif_output"],
                    b_factor_type=BFactorType.PLDDT,
                    metrics=_metrics_from_output(output),
                    source="boltz2-pair-scaled",
                )
                structures.append(
                    normalize_output_chain_ids(structure, sp_complex.chains)
                )
    return structures


def boltz2_pair_scaling_backend(sequences: list[str], request: Any) -> list[Structure]:
    """Prepare paper inputs and dispatch the audited Boltz backend locally or on Modal."""

    config = _boltz_config(request)
    inputs, config = _prepare_inputs(sequences, config)
    if os.environ.get(PAIR_SCALING_EXECUTION_ENV) == "local":
        return run_prepared_pair_scaled_boltz2(inputs, config, beta=request.beta)

    from proto_tools.modal import client as modal_client
    from proto_tools.modal.app import resolve_environment

    # Resolve through proto-tools' bound-method seam instead of looking the
    # class up directly.  ProtoFuse's paired evaluator scopes that seam with
    # one explicit accelerator, container pool, retry policy, and warm window;
    # bypassing it would make the custom backend's reported hardware policy
    # differ from the service that actually ran.
    predict = modal_client._bound_method(  # noqa: SLF001 - shared Modal dispatch seam
        PAIR_SCALING_MODAL_APP,
        PAIR_SCALING_MODAL_CLASS,
        "predict",
        PAIR_SCALING_MODAL_TOOL_KEY,
        environment=resolve_environment(),
    )
    payload = predict.remote(
        inputs.model_dump(mode="json"),
        config.model_dump(mode="json"),
        request.beta,
    )
    if not isinstance(payload, list):
        raise RuntimeError("pair-scaled Boltz Modal service returned an invalid payload")
    return [Structure.model_validate(item) for item in payload]
