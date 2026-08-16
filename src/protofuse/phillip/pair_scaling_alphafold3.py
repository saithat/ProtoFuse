"""Reviewed AlphaFold 3 v3.0.1 backend for pair-representation scaling."""

from __future__ import annotations

from typing import Any

import modal
from proto_tools import Structure
from proto_tools.tools.structure_prediction.alphafold3.alphafold3 import (
    AlphaFold3Config,
    AlphaFold3Input,
)
from proto_tools.tools.structure_prediction.shared_data_models import (
    Chain,
    Complex,
)

from protofuse.phillip.pair_scaling_msa import load_paper_server_msa
from protofuse.phillip.pair_scaling_values import validate_paper_beta

PAIR_SCALING_MODAL_APP = "protofuse-pair-scaling-af3"
PAIR_SCALING_MODAL_CLASS = "PairScalingAlphaFold3Service"
def _af3_config(request: Any) -> AlphaFold3Config:
    """Translate the paper contract without silently changing AF3 defaults."""

    validate_paper_beta(request.beta)
    if request.sampling_steps != 200:
        raise ValueError("AlphaFold 3 v3.0.1 backend requires the paper-default 200 steps")
    if request.step_scale != 1.5:
        raise ValueError("AlphaFold 3 v3.0.1 backend requires paper step_scale=1.5")
    if request.max_msa_seqs != 1024 and request.use_msa:
        raise ValueError("paper AlphaFold 3 inference requires an MSA depth of 1024")
    return AlphaFold3Config(
        name="protofuse_pair_scaled_af3",
        seed=request.model_seed,
        seeds=[request.model_seed],
        num_recycles=request.recycling_steps,
        num_diffusion_samples=request.diffusion_samples,
        use_msa=request.use_msa,
        include_pae_matrix=False,
        device="cuda",
    )


def _prepare_inputs(
    sequences: list[str],
    config: AlphaFold3Config,
) -> AlphaFold3Input:
    """Map repeated proposals to one seeded call returning every diffusion sample."""

    if not sequences:
        raise ValueError("pair-scaling requires at least one fixed-sequence draw")
    if len(set(sequences)) != 1:
        raise ValueError(
            "pair-scaling diffusion draws must all use the same fixed sequence"
        )
    if len(sequences) != config.num_diffusion_samples:
        raise ValueError(
            "pair-scaling proposal count must equal num_diffusion_samples so every "
            "paper draw comes from one seeded diffusion batch"
        )
    complex_input = Complex(
        chains=[Chain(sequence=sequences[0], entity_type="protein")]
    )
    msas = [load_paper_server_msa(sequences[0])] if config.use_msa else None
    return AlphaFold3Input(complexes=[complex_input], msas=msas)


def alphafold3_pair_scaling_backend(
    sequences: list[str],
    request: Any,
) -> list[Structure]:
    """Dispatch the pinned, patched AF3 v3.0.1 service and fail closed on drift."""

    config = _af3_config(request)
    inputs = _prepare_inputs(sequences, config)

    from proto_tools.modal.app import resolve_environment

    service = modal.Cls.from_name(
        PAIR_SCALING_MODAL_APP,
        PAIR_SCALING_MODAL_CLASS,
        environment_name=resolve_environment(),
    )()
    payload = service.predict.remote(
        inputs.model_dump(mode="json"),
        config.model_dump(mode="json"),
        request.beta,
    )
    if not isinstance(payload, list) or len(payload) != len(sequences):
        raise RuntimeError(
            "pair-scaled AlphaFold 3 service did not return every requested "
            "diffusion sample"
        )
    return [Structure.model_validate(item) for item in payload]
