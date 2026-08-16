"""Conditioning helpers for protein cycling optimizers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from proto_language.core import Sequence
from proto_tools import (
    Chain,
    Complex,
    InverseFoldingStructureInput,
    RFdiffusion3Config,
    RFdiffusion3DesignSpec,
    RFdiffusion3Input,
    Structure,
    predict_structures,
    run_rfdiffusion3,
)
from proto_tools.entities.structures.selection import ChainSelection


def _binder_chain_id(structure: Structure, target_chains: list[str]) -> str:
    chain_ids = structure.get_chain_ids()
    for chain_id in reversed(chain_ids):
        if chain_id not in target_chains:
            return chain_id
    return chain_ids[-1]


def _inverse_folding_input_from_complex(
    structure: Structure,
    *,
    target_chains: list[str],
) -> InverseFoldingStructureInput:
    binder_chain = _binder_chain_id(structure, target_chains)
    return InverseFoldingStructureInput(
        structure=structure,
        chains_to_redesign=ChainSelection(chains=[binder_chain]),
    )


def _contiguous_position_spans(positions: list[int]) -> list[tuple[int, int]]:
    """Collapse observed residue numbers into spans without inventing missing residues."""

    if not positions:
        return []
    spans: list[tuple[int, int]] = []
    start = end = positions[0]
    for position in positions[1:]:
        if position == end + 1:
            end = position
            continue
        spans.append((start, end))
        start = end = position
    spans.append((start, end))
    return spans


def _resolved_target_contig(
    structure: Structure,
    *,
    target_chains: list[str],
    binder_length: int,
) -> str:
    """Build a fixed-target contig from residues that actually exist in the structure."""

    target_segments: list[str] = []
    for chain_id in target_chains:
        positions = structure.get_chain_positions(chain_id)
        if not positions:
            raise ValueError(f"Target chain {chain_id!r} has no polymer residues.")
        target_segments.extend(
            f"{chain_id}{start}-{end}"
            for start, end in _contiguous_position_spans(positions)
        )
    return ",".join(target_segments) + f",/0,{binder_length}"


def make_rfdiffusion_boltz_cycling_conditioning_fn(
    *,
    target_sequence: str,
    target_structure: Structure,
    target_chains: list[str],
    hotspots: list[str],
    binder_length: int,
    structure_tool: str = "boltz2",
) -> Callable[[list[Sequence]], list[InverseFoldingStructureInput]]:
    """Bootstrap with RFdiffusion3+MPNN, then re-fold binder+target with Boltz-2 each cycle."""

    target_contig = _resolved_target_contig(
        target_structure,
        target_chains=target_chains,
        binder_length=binder_length,
    )

    def _bootstrap_structure() -> InverseFoldingStructureInput:
        result = run_rfdiffusion3(
            inputs=RFdiffusion3Input(
                design_specs=[
                    RFdiffusion3DesignSpec(
                        input_structure=target_structure,
                        contig=target_contig,
                        select_hotspots=",".join(hotspots) if hotspots else None,
                        infer_ori_strategy="hotspots" if hotspots else None,
                    )
                ]
            ),
            config=RFdiffusion3Config(),
        )
        if not result.designed_structures or not result.designed_structures[0].structures:
            raise RuntimeError(
                f"RFdiffusion3 produced no binder backbones for contig {target_contig!r}."
            )
        structure = result.designed_structures[0].structures[0].structure
        return _inverse_folding_input_from_complex(
            structure,
            target_chains=target_chains,
        )

    def conditioning_fn(sequences: list[Sequence]) -> list[InverseFoldingStructureInput]:
        outputs: list[InverseFoldingStructureInput] = []
        for sequence in sequences:
            sequence_text = sequence.sequence or ""
            if not sequence_text.strip("X") or sequence.structure is None:
                outputs.append(_bootstrap_structure())
                continue

            complex_input = Complex(
                chains=[
                    Chain(sequence=sequence_text, entity_type="protein"),
                    Chain(sequence=target_sequence, entity_type="protein"),
                ]
            )
            folded = predict_structures(
                [complex_input], structure_tool, {"use_msa": False}
            ).structures[0]
            sequence.structure = folded
            outputs.append(
                InverseFoldingStructureInput(
                    structure=folded,
                    chains_to_redesign=ChainSelection(chains=["A"]),
                )
            )
        return outputs

    return conditioning_fn


def bioemu_constraint_config(
    *,
    target_structure: Structure | str,
    target_chain_id: str,
    num_samples: int,
    max_ensemble_rmsd: float,
    model_seed: int,
) -> dict[str, Any]:
    """Build function_config for structure_ensemble_rmsd_constraint."""

    return {
        "target_structure": target_structure,
        "target_chain_id": target_chain_id,
        "bioemu_config": {
            "num_samples": num_samples,
            "batch_size": min(num_samples, 4),
            "seed": model_seed,
        },
        "inflection_point_angstroms": max_ensemble_rmsd,
        "verbose": False,
    }
