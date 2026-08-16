"""Paper-exact Enformer and Borzoi objectives for the Evo 2 regulatory design."""

from __future__ import annotations

import numpy as np
from proto_language.constraint import (
    BorzoiChromatinAccessibilityMorseConfig,
    EnformerChromatinAccessibilityMorseConfig,
)
from proto_language.constraint.constraint_registry import constraint
from proto_language.constraint.sequence_annotation.chromatin_accessibility_morse_utils import (
    build_binary_pattern_for_target,
    compute_morse_windows,
    prepare_context_padded_candidate,
    slice_signal,
)
from proto_language.core import ConstraintOutput, Sequence
from proto_tools.tools.sequence_scoring.borzoi import (
    BORZOI_CONTEXT,
    BORZOI_OUTPUT_FLANK,
    BorzoiEnsembleConfig,
    BorzoiInput,
    run_borzoi_ensemble,
)
from proto_tools.tools.sequence_scoring.enformer import (
    ENFORMER_CONTEXT,
    ENFORMER_OUTPUT_FLANK,
    EnformerConfig,
    EnformerInput,
    run_enformer,
)
from proto_tools.tools.sequence_scoring.shared_data_models import (
    SequenceTargetRange,
    SequenceWindow,
)


def _pattern(config: object) -> list[tuple[int, int]]:
    typed_config = config
    if not isinstance(
        typed_config,
        (EnformerChromatinAccessibilityMorseConfig, BorzoiChromatinAccessibilityMorseConfig),
    ):
        raise TypeError("unexpected Evo 2 paper constraint configuration")
    highs, _ = compute_morse_windows(
        pattern=typed_config.pattern,
        pattern_start_bp=typed_config.pattern_start_bp,
        dot_bp=typed_config.dot_bp,
        dash_bp=typed_config.dash_bp,
        intra_symbol_gap_bp=typed_config.intra_symbol_gap_bp,
        inter_letter_gap_bp=typed_config.inter_letter_gap_bp,
    )
    return highs


def _l1_output(
    *,
    model_name: str,
    normalized_signal: np.ndarray,
    target_start: int,
    target_end: int,
    output_start: int,
    resolution: float,
    highs: list[tuple[int, int]],
    normalization_denom: float,
) -> ConstraintOutput:
    target_signal = slice_signal(
        normalized_signal,
        target_start,
        target_end,
        output_start,
        resolution,
    )
    if target_signal.size == 0:
        raise ValueError(f"{model_name} scoring found no output bins for the designed interval")
    pattern = build_binary_pattern_for_target(
        highs,
        target_num_bins=len(target_signal),
        resolution=resolution,
    )
    l1_sum = float(np.sum(np.abs(pattern - target_signal)))
    return ConstraintOutput(
        score=l1_sum,
        metadata={
            "paper_model": model_name.lower(),
            "paper_loss": "l1_sum",
            "paper_l1_sum": l1_sum,
            "paper_target_bins": int(target_signal.size),
            "paper_output_resolution_bp": resolution,
            "paper_normalization_denom": normalization_denom,
        },
        metadata_recipient="Target",
    )


@constraint(
    key="evo2-paper-enformer-l1",
    label="Evo 2 Paper Enformer L1",
    config=EnformerChromatinAccessibilityMorseConfig,
    description="Paper-exact global-max-normalized Enformer L1 sum on the designed interval",
    uses_gpu=True,
    tools_called=["enformer-prediction"],
    category="sequence_annotation",
    supported_sequence_types=["dna"],
    input_labels=["Left Flank", "Target", "Right Flank"],
)
def evo2_paper_enformer_l1_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: EnformerChromatinAccessibilityMorseConfig,
) -> list[ConstraintOutput]:
    """Compute the paper's Enformer L1 sum rather than Proto's mean-error proxy."""

    if not input_sequences:
        return []
    if len(config.enformer_output_tracks) != 1:
        raise ValueError("the reviewed paper objective requires exactly one Enformer DNase track")
    prepared = [
        prepare_context_padded_candidate(
            candidate,
            trim_prefix_bp=config.trim_prefix_bp,
            output_flank=ENFORMER_OUTPUT_FLANK,
            context_length=ENFORMER_CONTEXT,
            model_name="Enformer",
        )
        for candidate in input_sequences
    ]
    result = run_enformer(
        EnformerInput(
            sequences=[
                SequenceWindow(
                    sequence=sequence,
                    target_range=SequenceTargetRange(start=start, end=end),
                )
                for sequence, start, end in prepared
            ]
        ),
        EnformerConfig(
            output_tracks=config.enformer_output_tracks,
            species=config.organism,
            batch_size=config.batch_size,
            device=config.device,
        ),
    )
    highs = _pattern(config)
    outputs: list[ConstraintOutput] = []
    for (_, target_start, target_end), prediction in zip(
        prepared, result.results, strict=True
    ):
        values = np.asarray(prediction.prediction, dtype=np.float32)
        if values.ndim != 2 or values.shape[1] != 1:
            raise ValueError(f"unexpected Enformer prediction shape: {values.shape}")
        denom = float(np.max(values)) if values.size else 0.0
        normalized = values[:, 0] / denom if denom > 0.0 else np.zeros(values.shape[0])
        outputs.append(
            _l1_output(
                model_name="enformer",
                normalized_signal=np.asarray(normalized, dtype=np.float32),
                target_start=target_start,
                target_end=target_end,
                output_start=prediction.output_start,
                resolution=float(prediction.output_resolution),
                highs=highs,
                normalization_denom=denom,
            )
        )
    return outputs


evo2_paper_enformer_l1_constraint._constraint_allow_raw_scores = True  # type: ignore[attr-defined]


@constraint(
    key="evo2-paper-borzoi-l1",
    label="Evo 2 Paper Borzoi L1",
    config=BorzoiChromatinAccessibilityMorseConfig,
    description="Paper-exact shared-max-normalized four-model Borzoi LCB L1 sum",
    uses_gpu=True,
    tools_called=["borzoi-ensemble"],
    category="sequence_annotation",
    supported_sequence_types=["dna"],
    input_labels=["Left Flank", "Target", "Right Flank"],
)
def evo2_paper_borzoi_l1_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: BorzoiChromatinAccessibilityMorseConfig,
) -> list[ConstraintOutput]:
    """Compute normalization before the paper's four-replicate lower confidence bound."""

    if not input_sequences:
        return []
    if len(config.borzoi_output_tracks) != 1:
        raise ValueError("the reviewed paper objective requires exactly one Borzoi DNase track")
    prepared = [
        prepare_context_padded_candidate(
            candidate,
            trim_prefix_bp=config.trim_prefix_bp,
            output_flank=BORZOI_OUTPUT_FLANK,
            context_length=BORZOI_CONTEXT,
            model_name="Borzoi",
        )
        for candidate in input_sequences
    ]
    result = run_borzoi_ensemble(
        BorzoiInput(
            sequences=[
                SequenceWindow(
                    sequence=sequence,
                    target_range=SequenceTargetRange(start=start, end=end),
                )
                for sequence, start, end in prepared
            ]
        ),
        BorzoiEnsembleConfig(
            output_tracks=config.borzoi_output_tracks,
            species=config.organism,
            avg_output_tracks=False,
            batch_size=config.batch_size,
            device=config.device,
        ),
    )
    highs = _pattern(config)
    outputs: list[ConstraintOutput] = []
    for (_, target_start, target_end), prediction in zip(
        prepared, result.results, strict=True
    ):
        values = np.asarray(prediction.predictions, dtype=np.float32)
        if values.ndim != 3 or values.shape[0] != 4 or values.shape[1] != 1:
            raise ValueError(f"unexpected Borzoi ensemble prediction shape: {values.shape}")
        denom = float(np.max(values)) if values.size else 0.0
        normalized = values / denom if denom > 0.0 else np.zeros_like(values)
        replicate_signals = normalized[:, 0, :]
        lower_confidence_bound = replicate_signals.mean(axis=0) - replicate_signals.std(
            axis=0
        )
        outputs.append(
            _l1_output(
                model_name="borzoi",
                normalized_signal=np.asarray(lower_confidence_bound, dtype=np.float32),
                target_start=target_start,
                target_end=target_end,
                output_start=prediction.output_start,
                resolution=float(prediction.output_resolution),
                highs=highs,
                normalization_denom=denom,
            )
        )
    return outputs


evo2_paper_borzoi_l1_constraint._constraint_allow_raw_scores = True  # type: ignore[attr-defined]
