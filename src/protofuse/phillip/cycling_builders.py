"""Conditioning helpers for protein cycling optimizers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from proto_language.core import Segment, Sequence
from proto_language.generator import (
    RFdiffusionMPNNBinderGenerator,
    RFdiffusionMPNNBinderGeneratorConfig,
)
from proto_tools import Chain, Complex, InverseFoldingStructureInput, Structure, predict_structures
from proto_tools.entities.structures.selection import ChainSelection, ResidueSelection


def _binder_chain_id(structure: Structure, target_chains: list[str]) -> str:
    chain_ids = structure.get_chain_ids()
    for chain_id in reversed(chain_ids):
        if chain_id not in target_chains:
            return chain_id
    return chain_ids[-1]


def _fixed_target_positions(structure: Structure, target_chains: list[str]) -> dict[str, list[int]]:
    fixed: dict[str, list[int]] = {}
    for chain_id in target_chains:
        fixed[chain_id] = list(range(1, len(structure.get_chain_positions(chain_id)) + 1))
    return fixed


def _inverse_folding_input_from_complex(
    structure: Structure,
    *,
    target_chains: list[str],
) -> InverseFoldingStructureInput:
    binder_chain = _binder_chain_id(structure, target_chains)
    return InverseFoldingStructureInput(
        structure=structure,
        chains_to_redesign=ChainSelection(chains=[binder_chain]),
        fixed_positions=ResidueSelection(chains=_fixed_target_positions(structure, target_chains)),
    )


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

    rfdiffusion_config = RFdiffusionMPNNBinderGeneratorConfig(
        target_structure=target_structure,
        target_chains=target_chains,
        hotspots=hotspots,
    )

    def _bootstrap_structure() -> InverseFoldingStructureInput:
        bootstrap_binder = Segment(length=binder_length, sequence_type="protein", label="binder")
        generator = RFdiffusionMPNNBinderGenerator(rfdiffusion_config)
        generator.assign(bootstrap_binder)
        bootstrap_binder.proposal_sequences = [
            Sequence(sequence="X" * binder_length, sequence_type="protein")
        ]
        generator.sample()
        proposal = bootstrap_binder.proposal_sequences[0]
        if proposal.structure is None:
            raise RuntimeError("RFdiffusionMPNN bootstrap did not attach a binder-target structure")
        return _inverse_folding_input_from_complex(
            proposal.structure,
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
                    fixed_positions=ResidueSelection(
                        chains={"B": list(range(1, len(target_sequence) + 1))}
                    ),
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
) -> dict[str, Any]:
    """Build function_config for structure_ensemble_rmsd_constraint."""

    return {
        "target_structure": target_structure,
        "target_chain_id": target_chain_id,
        "bioemu_config": {
            "num_samples": num_samples,
            "batch_size": min(num_samples, 4),
        },
        "inflection_point_angstroms": max_ensemble_rmsd,
        "verbose": False,
    }
