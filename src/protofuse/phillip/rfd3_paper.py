"""Paper-specific RFDiffusion3 generation and AlphaFold3 success scoring."""

from __future__ import annotations

from math import ceil
from typing import Any

import numpy as np
from proto_language.constraint.constraint_registry import constraint
from proto_language.core import ConstraintOutput, Generator, Sequence
from proto_language.core.generator import GeneratorInputType
from proto_language.generator.generator_registry import generator
from proto_language.utils.base import BaseConfig, ConfigField
from proto_tools import (
    AlphaFold3Config,
    Complex,
    InverseFoldingInput,
    InverseFoldingStructureInput,
    ProteinMPNNSampleConfig,
    RFdiffusion3Config,
    RFdiffusion3DesignSpec,
    RFdiffusion3Input,
    Structure,
    predict_structures,
    run_proteinmpnn_sample,
    run_rfdiffusion3,
)
from proto_tools.entities.structures.selection import ChainSelection


def _parse_residue_spans(value: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    for token in value.replace("/", ",").split(","):
        token = token.strip()
        if not token or len(token) < 4 or "-" not in token:
            raise ValueError(f"invalid target residue span: {token!r}")
        chain_id = token[0]
        start_text, end_text = token[1:].split("-", maxsplit=1)
        start, end = int(start_text), int(end_text)
        if end < start:
            raise ValueError(f"invalid target residue span: {token!r}")
        spans.append((chain_id, start, end))
    if not spans:
        raise ValueError("at least one target residue span is required")
    return spans


def crop_target_structure(structure: Structure, residue_spans: str) -> Structure:
    """Crop an RCSB asymmetric unit to the paper's inclusive author-numbered spans."""

    spans = _parse_residue_spans(residue_spans)
    allowed: dict[str, list[tuple[int, int]]] = {}
    for chain_id, start, end in spans:
        allowed.setdefault(chain_id, []).append((start, end))

    cropped = structure.gemmi_struct.clone()
    for model in cropped:
        for chain_index in range(len(model) - 1, -1, -1):
            chain = model[chain_index]
            ranges = allowed.get(chain.name)
            if ranges is None:
                del model[chain_index]
                continue
            for residue_index in range(len(chain) - 1, -1, -1):
                position = chain[residue_index].seqid.num
                if position is None or not any(
                    start <= position <= end for start, end in ranges
                ):
                    del chain[residue_index]

    result = Structure(
        structure=cropped.make_pdb_string(),
        structure_format="pdb",
        source=structure.source,
    )
    for chain_id, start, end in spans:
        observed = set(result.get_chain_positions(chain_id))
        if not observed.intersection(range(start, end + 1)):
            raise ValueError(
                f"cropped structure is missing registered span {chain_id}{start}-{end}"
            )
    return result


def target_sequence_from_cropped_structure(structure: Structure, chain_ids: list[str]) -> str:
    """Concatenate the cropped target-chain sequences in their registered order."""

    sequence = "".join(
        structure.get_chain_sequence(chain_id, remove_non_standard=True)
        for chain_id in chain_ids
    )
    if not sequence:
        raise ValueError("cropped target structure contains no standard protein sequence")
    return sequence


def paper_binder_origin(
    structure: Structure,
    atom_hotspots: dict[str, list[str]],
) -> list[float]:
    """Reproduce the paper's hotspot-directed binder center-of-mass initialization."""

    if len(structure.gemmi_struct) == 0:
        raise ValueError("target structure has no models")
    model = structure.gemmi_struct[0]
    all_atoms: list[np.ndarray] = []
    hotspot_atoms: list[np.ndarray] = []
    for chain in model:
        for residue in chain:
            residue_key = f"{chain.name}{residue.seqid.num}"
            selected_names = set(atom_hotspots.get(residue_key, []))
            # RCSB entries may contain alternate locations. RFD3 receives one physical
            # atom per name after preprocessing, so use the highest-occupancy conformer.
            atoms_by_name: dict[str, Any] = {}
            for atom in residue:
                atom_name = atom.name.strip()
                current = atoms_by_name.get(atom_name)
                if current is None or atom.occ > current.occ:
                    atoms_by_name[atom_name] = atom
            for atom_name, atom in atoms_by_name.items():
                coordinate = np.array([atom.pos.x, atom.pos.y, atom.pos.z], dtype=np.float64)
                all_atoms.append(coordinate)
                if atom_name in selected_names:
                    hotspot_atoms.append(coordinate)
    expected_atoms = sum(len(names) for names in atom_hotspots.values())
    if len(hotspot_atoms) != expected_atoms:
        raise ValueError(
            f"resolved {len(hotspot_atoms)} of {expected_atoms} registered hotspot atoms"
        )
    atom_matrix = np.stack(all_atoms)
    hotspot_matrix = np.stack(hotspot_atoms)
    within_12 = np.any(
        np.linalg.norm(atom_matrix[:, None, :] - hotspot_matrix[None, :, :], axis=2) <= 12.0,
        axis=1,
    )
    nearby_mean = atom_matrix[within_12].mean(axis=0)
    hotspot_mean = hotspot_matrix.mean(axis=0)
    direction = hotspot_mean - nearby_mean
    magnitude = float(np.linalg.norm(direction))
    if magnitude <= 1e-12:
        raise ValueError("paper binder-origin direction is undefined for coincident atom means")
    return [float(value) for value in hotspot_mean + (10.0 * direction / magnitude)]


class RFD3PaperBinderGeneratorConfig(BaseConfig):
    """Exact fixed-length member of one paper target's RFD3 design campaign."""

    target_structure: Structure | str = ConfigField(
        title="Cropped target structure",
        description="Unrelaxed RCSB asymmetric unit cropped to the paper's residue spans.",
    )
    target_contig: str = ConfigField(
        title="Target contig",
        description="Inclusive target spans followed by the fixed prototype binder length.",
    )
    atom_hotspots: dict[str, list[str]] = ConfigField(
        title="Atom hotspots",
        description="Paper Table S6 atom selections keyed by author-numbered residue.",
    )
    binder_origin: list[float] = ConfigField(
        title="Binder origin",
        description="Paper hotspot-derived center-of-mass initialization in Angstroms.",
        min_length=3,
        max_length=3,
    )
    rfdiffusion3_config: RFdiffusion3Config = ConfigField(
        default_factory=RFdiffusion3Config,
        title="RFdiffusion3 config",
        description="Backbone-generation settings.",
    )
    proteinmpnn_config: ProteinMPNNSampleConfig = ConfigField(
        default_factory=ProteinMPNNSampleConfig,
        title="ProteinMPNN config",
        description="Four-sequence inverse-folding settings.",
    )


@generator(
    key="rfd3-paper-ppi-binder",
    label="RFDiffusion3 Paper PPI Binder",
    config=RFD3PaperBinderGeneratorConfig,
    description="RFD3 PPI generation with exact target crop, atom hotspots, and binder origin",
    uses_gpu=True,
    tools_called=["rfdiffusion3-design", "proteinmpnn-sample"],
    supported_sequence_types=["protein"],
)
class RFD3PaperBinderGenerator(Generator):
    """Generate fixed-length campaign members using the paper's complete conditioning."""

    input_type = GeneratorInputType.STARTING_SEQUENCE
    allows_empty_starting_sequence = True
    batch_size = 1

    def __init__(self, config: RFD3PaperBinderGeneratorConfig) -> None:
        super().__init__()
        self.config = config

    def _preserve_structure_after_sample(self) -> bool:
        return True

    def _sample(self) -> None:
        target_structure = self.config.target_structure
        if isinstance(target_structure, str):
            target_structure = Structure(structure=target_structure)
        segment = self.segment
        if not any(proposal.sequence for proposal in segment.proposal_sequences):
            for proposal in segment.proposal_sequences:
                proposal.sequence = "X" * segment.sequence_length
        self._validate_generator()

        sequences_per_backbone = self.config.proteinmpnn_config.num_sequences_per_structure
        num_backbones = ceil(segment.num_proposals / sequences_per_backbone)
        n_batches = ceil(
            num_backbones / self.config.rfdiffusion3_config.diffusion_batch_size
        )
        rfd_config = self.config.rfdiffusion3_config.model_copy(
            update={"n_batches": n_batches, "seed": self._next_seed()}
        )
        rfd_output = run_rfdiffusion3(
            inputs=RFdiffusion3Input(
                design_specs=[
                    RFdiffusion3DesignSpec(
                        input_structure=target_structure,
                        contig=self.config.target_contig,
                        select_hotspots={
                            residue: ",".join(atoms)
                            for residue, atoms in self.config.atom_hotspots.items()
                        },
                        ori_token=self.config.binder_origin,
                    )
                ]
            ),
            config=rfd_config,
        )
        backbones = list(rfd_output.designed_structures[0])[:num_backbones]
        if not backbones:
            raise RuntimeError("RFdiffusion3 produced no PPI backbones")
        structure_inputs = [
            InverseFoldingStructureInput(
                structure=backbone.structure,
                chains_to_redesign=ChainSelection(
                    chains=[backbone.structure.get_chain_ids()[-1]]
                ),
            )
            for backbone in backbones
        ]
        mpnn_output = run_proteinmpnn_sample(
            inputs=InverseFoldingInput(inputs=structure_inputs),
            config=self.config.proteinmpnn_config.model_copy(update={"seed": self._next_seed()}),
        )

        records: list[tuple[str, Structure, dict[str, Any]]] = []
        for backbone, structure_input, design_set in zip(
            backbones, structure_inputs, mpnn_output.design_sets, strict=True
        ):
            binder_chain_id = structure_input.chain_ids_to_redesign[0]
            for design in design_set.complexes:
                binder_sequence = next(
                    chain.sequence
                    for chain, was_designed in zip(design.chains, design.designed, strict=True)
                    if was_designed and chain.id == binder_chain_id
                )
                records.append((binder_sequence, backbone.structure, dict(design.metrics.items())))
        if len(records) < segment.num_proposals:
            raise RuntimeError("RFD3/ProteinMPNN returned fewer designs than requested")
        for proposal, (sequence, structure, metrics) in zip(
            segment.proposal_sequences, records[: segment.num_proposals], strict=True
        ):
            proposal.sequence = sequence
            proposal.structure = structure
            proposal._generator_metadata[self._spec.key] = {
                "contig": self.config.target_contig,
                "atom_hotspots": self.config.atom_hotspots,
                "binder_origin": self.config.binder_origin,
                "perplexity": metrics.get("perplexity"),
                "sequence_recovery": metrics.get("sequence_recovery"),
            }


class RFD3AF3PaperSuccessConfig(BaseConfig):
    """The paper's conjunctive AF3 PPI success thresholds."""

    alphafold3_config: AlphaFold3Config = ConfigField(
        default_factory=lambda: AlphaFold3Config(include_pae_matrix=True),
        title="AlphaFold3 config",
        description="AF3 must return its complete PAE and per-chain confidence matrix.",
    )
    max_min_interchain_pae: float = ConfigField(
        default=1.5,
        ge=0.0,
        title="Maximum minimum interchain PAE",
        description="Paper cutoff for the smallest cross-chain AF3 PAE value.",
    )
    min_binder_ptm: float = ConfigField(
        default=0.8,
        ge=0.0,
        le=1.0,
        title="Minimum binder pTM",
        description="Paper cutoff for AF3 pTM restricted to the binder chain.",
    )
    max_target_aligned_binder_ca_rmsd: float = ConfigField(
        default=2.5,
        ge=0.0,
        title="Maximum binder RMSD",
        description="Paper cutoff for target-aligned binder C-alpha RMSD in Angstroms.",
    )


def _kabsch_target_aligned_binder_rmsd(
    designed: Structure,
    predicted: Structure,
) -> float:
    designed_chains = list(designed.ca_coordinates_by_chain().values())
    predicted_chains = list(predicted.ca_coordinates_by_chain().values())
    if len(designed_chains) < 2 or len(predicted_chains) < 2:
        raise ValueError("RFD3 and AF3 complexes must each contain target and binder chains")
    designed_target = np.asarray(
        [coordinate for chain in designed_chains[:-1] for coordinate in chain],
        dtype=np.float64,
    )
    designed_binder = np.asarray(designed_chains[-1], dtype=np.float64)
    predicted_binder = np.asarray(predicted_chains[0], dtype=np.float64)
    predicted_target = np.asarray(
        [coordinate for chain in predicted_chains[1:] for coordinate in chain],
        dtype=np.float64,
    )
    if designed_target.shape != predicted_target.shape:
        raise ValueError(
            "target CA correspondence mismatch: "
            f"{designed_target.shape} vs {predicted_target.shape}"
        )
    if designed_binder.shape != predicted_binder.shape:
        raise ValueError(
            "binder CA correspondence mismatch: "
            f"{designed_binder.shape} vs {predicted_binder.shape}"
        )
    mobile_center = predicted_target.mean(axis=0)
    reference_center = designed_target.mean(axis=0)
    mobile = predicted_target - mobile_center
    reference = designed_target - reference_center
    left, _, right = np.linalg.svd(mobile.T @ reference)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    aligned_binder = (predicted_binder - mobile_center) @ rotation + reference_center
    return float(np.sqrt(np.mean(np.sum((aligned_binder - designed_binder) ** 2, axis=1))))


@constraint(
    key="rfd3-af3-paper-success",
    label="RFD3 AF3 Paper Success",
    config=RFD3AF3PaperSuccessConfig,
    description="Conjunctive binder-pTM, minimum interchain PAE, and target-aligned RMSD gate",
    uses_gpu=True,
    tools_called=["alphafold3-prediction"],
    category="protein_structure",
    supported_sequence_types=["protein"],
    input_labels=["binder", "target"],
)
def rfd3_af3_paper_success_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: RFD3AF3PaperSuccessConfig,
) -> list[ConstraintOutput]:
    """Run AF3 once and evaluate all three paper endpoints on each prediction."""

    if not config.alphafold3_config.include_pae_matrix:
        raise ValueError("the paper success gate requires include_pae_matrix=True")
    complexes = [
        Complex.model_validate(
            {
                "chains": [
                    {"sequence": sequence.sequence, "entity_type": sequence.sequence_type}
                    for sequence in candidate
                ]
            }
        )
        for candidate in input_sequences
    ]
    prediction = predict_structures(complexes, "alphafold3", config.alphafold3_config)
    outputs: list[ConstraintOutput] = []
    for candidate, predicted in zip(input_sequences, prediction.structures, strict=True):
        binder, _target = candidate
        if binder.structure is None:
            raise ValueError("RFD3 proposal structure is required for target-aligned binder RMSD")
        metrics = dict(predicted.metrics.items())
        pae = np.asarray(metrics.get("pae"), dtype=np.float64)
        binder_length = len(binder.sequence)
        total_length = sum(len(sequence.sequence) for sequence in candidate)
        if pae.shape != (total_length, total_length):
            raise ValueError(f"unexpected AF3 PAE shape: {pae.shape}")
        cross_pae = np.concatenate(
            (
                pae[:binder_length, binder_length:].ravel(),
                pae[binder_length:, :binder_length].ravel(),
            )
        )
        minimum_interchain_pae = float(np.min(cross_pae))
        chain_pair_iptm = np.asarray(metrics.get("chain_pair_iptm"), dtype=np.float64)
        if chain_pair_iptm.ndim != 2 or chain_pair_iptm.shape[0] < 2:
            raise ValueError("AF3 did not return its per-chain confidence matrix")
        # AF3 documents diagonal chain_pair_iptm entries as the pTM restricted to each chain.
        binder_ptm = float(chain_pair_iptm[0, 0])
        binder_rmsd = _kabsch_target_aligned_binder_rmsd(binder.structure, predicted)
        excess = max(
            0.0,
            minimum_interchain_pae / config.max_min_interchain_pae - 1.0,
            config.min_binder_ptm / max(binder_ptm, 1e-12) - 1.0,
            binder_rmsd / config.max_target_aligned_binder_ca_rmsd - 1.0,
        )
        outputs.append(
            ConstraintOutput(
                score=float(excess),
                metadata={
                    "minimum_interchain_pae": minimum_interchain_pae,
                    "binder_ptm": binder_ptm,
                    "target_aligned_binder_ca_rmsd": binder_rmsd,
                    "paper_success": excess == 0.0,
                },
            )
        )
    return outputs


rfd3_af3_paper_success_constraint._constraint_allow_raw_scores = True  # type: ignore[attr-defined]
