"""Fail-closed contract for trusted pair-representation-scaling backends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Literal, cast

from proto_language.constraint.constraint_registry import constraint
from proto_language.core import ConstraintOutput, Sequence
from proto_language.utils.base import BaseConfig, ConfigField
from proto_tools import Structure, USalignConfig, USalignInput, run_usalign

from protofuse.execution_context import active_program_execution_cache

PairScalingModel = Literal["alphafold3", "boltz2"]


@dataclass(frozen=True)
class PairScalingBackendRequest:
    """Typed request passed only to an explicitly registered reviewed backend."""

    model: PairScalingModel
    beta: float
    model_seed: int
    recycling_steps: int
    sampling_steps: int
    diffusion_samples: int
    step_scale: float
    use_msa: bool
    max_msa_seqs: int
    subsample_msa: bool


PairScalingBackend = Callable[
    [list[str], PairScalingBackendRequest],
    list[Structure],
]

_BACKENDS: dict[PairScalingModel, PairScalingBackend] = {}
_PREDICTION_CACHE: dict[tuple[object, ...], list[Structure]] = {}
_BACKEND_LOCK = Lock()
_EXECUTION_CACHE_NAMESPACE = "protofuse.phillip.pair_scaling.predictions"


def register_reviewed_pair_scaling_backend(
    model: PairScalingModel,
    backend: PairScalingBackend,
) -> None:
    """Register a locally reviewed implementation; no dynamic imports or fallback are allowed."""

    with _BACKEND_LOCK:
        _BACKENDS[model] = backend
        _PREDICTION_CACHE.clear()


def clear_reviewed_pair_scaling_backends() -> None:
    """Clear registrations and cached predictions, primarily for isolated tests."""

    with _BACKEND_LOCK:
        _BACKENDS.clear()
        _PREDICTION_CACHE.clear()


def install_default_reviewed_pair_scaling_backends() -> None:
    """Install ProtoFuse's audited, fail-closed model backends."""

    from protofuse.phillip.pair_scaling_alphafold3 import (
        alphafold3_pair_scaling_backend,
    )
    from protofuse.phillip.pair_scaling_boltz2 import boltz2_pair_scaling_backend

    register_reviewed_pair_scaling_backend(
        "alphafold3", alphafold3_pair_scaling_backend
    )
    register_reviewed_pair_scaling_backend("boltz2", boltz2_pair_scaling_backend)


class PairScaledStateTMScoreConfig(BaseConfig):
    """One model, beta setting, seed, and reference-state comparison."""

    model: PairScalingModel = ConfigField(
        title="Pair-scaling model",
        description="Reviewed model backend to invoke.",
    )
    beta: float = ConfigField(
        title="Pair scale beta",
        description="Scale z by 1 + beta at every Pairformer recycle input.",
        ge=-0.75,
        le=0.75,
    )
    model_seed: int = ConfigField(
        title="Sampling seed",
        description=(
            "Model seed paired across full and fused arms; deliberately not named "
            "'seed' so Proto's per-constraint optimizer seeding cannot overwrite it."
        ),
        ge=0,
    )
    recycling_steps: int = ConfigField(
        title="Recycling steps",
        description="Number of model recycling iterations.",
        ge=1,
    )
    sampling_steps: int = ConfigField(
        title="Diffusion sampling steps",
        description="Number of Boltz diffusion denoising steps.",
        ge=1,
    )
    diffusion_samples: int = ConfigField(
        title="Diffusion samples",
        description="Number of structure samples produced per model call.",
        ge=1,
    )
    step_scale: float = ConfigField(
        title="Diffusion step scale",
        description="Boltz diffusion step scale used by the paper protocol.",
        gt=0.0,
    )
    use_msa: bool = ConfigField(
        title="Use MSA",
        description="Whether to generate and consume an MSA for this protocol tier.",
    )
    max_msa_seqs: int = ConfigField(
        title="Maximum MSA depth",
        description="Matched input-alignment depth for this benchmark slice.",
        ge=1,
    )
    subsample_msa: bool = ConfigField(
        title="Subsample MSA",
        description="Whether the registered backend subsamples the supplied alignment.",
    )
    target_structure: Structure | str = ConfigField(
        title="Reference state",
        description="Experimental structure used for US-align TM-score evaluation.",
    )
    reference_state: Literal["dominant", "alternative"] = ConfigField(
        title="Reference-state label",
        description="Stable label stored with the per-model metric.",
    )


def _predict(
    sequences: list[str],
    config: PairScaledStateTMScoreConfig,
) -> list[Structure]:
    request = PairScalingBackendRequest(
        model=config.model,
        beta=config.beta,
        model_seed=config.model_seed,
        recycling_steps=config.recycling_steps,
        sampling_steps=config.sampling_steps,
        diffusion_samples=config.diffusion_samples,
        step_scale=config.step_scale,
        use_msa=config.use_msa,
        max_msa_seqs=config.max_msa_seqs,
        subsample_msa=config.subsample_msa,
    )
    key: tuple[object, ...] = (
        request,
        tuple(sequences),
    )
    execution_cache = active_program_execution_cache()
    execution_key: tuple[object, ...] = (_EXECUTION_CACHE_NAMESPACE, *key)
    with _BACKEND_LOCK:
        cached = (
            _PREDICTION_CACHE.get(key)
            if execution_cache is None
            else cast(list[Structure] | None, execution_cache.get(execution_key))
        )
        backend = _BACKENDS.get(config.model)
    if cached is not None:
        return cached
    if backend is None:
        raise RuntimeError(
            f"No reviewed {config.model} pair-scaling backend is registered. "
            "ProtoFuse refuses to substitute unscaled structure prediction."
        )
    predictions = backend(sequences, request)
    if len(predictions) != len(sequences):
        raise RuntimeError(
            f"reviewed {config.model} backend returned {len(predictions)} structures "
            f"for {len(sequences)} requests"
        )
    with _BACKEND_LOCK:
        if execution_cache is None:
            _PREDICTION_CACHE[key] = predictions
        else:
            execution_cache[execution_key] = predictions
    return predictions


@constraint(
    key="pair-scaled-state-tmscore",
    label="Pair-Scaled State TM-score",
    config=PairScaledStateTMScoreConfig,
    description="Pair-scaled prediction scored against one experimental state with US-align",
    uses_gpu=True,
    tools_called=["reviewed-pair-scaling-backend", "usalign-alignment"],
    category="protein_structure",
    supported_sequence_types=["protein"],
)
def pair_scaled_state_tmscore_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: PairScaledStateTMScoreConfig,
) -> list[ConstraintOutput]:
    """Score one paper beta/seed slice and fail closed if the backend is unavailable."""

    sequences = [candidate[0].sequence for candidate in input_sequences]
    if any(len(candidate) != 1 for candidate in input_sequences):
        raise ValueError("pair-scaling state scoring expects one fixed protein input")
    target = (
        config.target_structure
        if isinstance(config.target_structure, Structure)
        else Structure(structure=config.target_structure)
    )
    predictions = _predict(sequences, config)
    outputs: list[ConstraintOutput] = []
    for prediction in predictions:
        alignment = run_usalign(
            USalignInput(query_structure=prediction, reference_structure=target),
            USalignConfig(),
        )
        tm_score = 0.5 * (
            float(alignment.metrics["tm_score_structure_1"])
            + float(alignment.metrics["tm_score_structure_2"])
        )
        outputs.append(
            ConstraintOutput(
                score=1.0 - tm_score,
                metadata={
                    "pair_scaling_model": config.model,
                    "pair_scaling_beta": config.beta,
                    "pair_scaling_seed": config.model_seed,
                    "reference_state": config.reference_state,
                    "tm_score": tm_score,
                },
                structures=(prediction,),
            )
        )
    return outputs


install_default_reviewed_pair_scaling_backends()
