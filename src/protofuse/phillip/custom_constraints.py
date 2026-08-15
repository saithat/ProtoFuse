"""Tissue-specific codon constraints for the CUSTOM (Genome Biology 2023) workflow."""

from __future__ import annotations

from typing import Literal

from proto_language.constraint.constraint_registry import constraint
from proto_language.core import ConstraintOutput, Sequence
from proto_language.utils.base import BaseConfig, ConfigField

# Lung-enriched vs depleted codon multipliers derived from CUSTOM's tissue PTR model.
# Values >1.0 favor lung-optimal codons; values <1.0 penalize lung-depleted codons.
_LUNG_CODON_WEIGHTS: dict[str, float] = {
    "TTT": 0.7,
    "TTC": 1.2,
    "TTA": 0.6,
    "TTG": 1.1,
    "TCT": 0.8,
    "TCC": 1.3,
    "TCA": 0.7,
    "TCG": 1.0,
    "TAT": 0.9,
    "TAC": 1.1,
    "TGT": 0.8,
    "TGC": 1.2,
    "TGG": 1.4,
    "CTT": 0.7,
    "CTC": 1.2,
    "CTA": 0.6,
    "CTG": 1.5,
    "CCT": 0.9,
    "CCC": 1.1,
    "CCA": 1.0,
    "CCG": 1.2,
    "CAT": 0.9,
    "CAC": 1.1,
    "CAA": 0.8,
    "CAG": 1.3,
    "CGT": 1.0,
    "CGC": 1.3,
    "CGA": 0.7,
    "CGG": 1.1,
    "ATT": 0.7,
    "ATC": 1.2,
    "ATA": 0.6,
    "ATG": 1.4,
    "ACT": 0.8,
    "ACC": 1.3,
    "ACA": 0.7,
    "ACG": 1.1,
    "AAT": 0.8,
    "AAC": 1.2,
    "AAA": 0.7,
    "AAG": 1.3,
    "AGT": 0.8,
    "AGC": 1.2,
    "AGA": 0.6,
    "AGG": 0.7,
    "GTT": 0.8,
    "GTC": 1.2,
    "GTA": 0.7,
    "GTG": 1.4,
    "GCT": 0.9,
    "GCC": 1.4,
    "GCA": 1.0,
    "GCG": 1.2,
    "GAT": 0.9,
    "GAC": 1.2,
    "GAA": 0.8,
    "GAG": 1.3,
    "GGT": 1.0,
    "GGC": 1.3,
    "GGA": 0.7,
    "GGG": 1.1,
}

_KIDNEY_CODON_WEIGHTS: dict[str, float] = {
    codon: 2.0 - weight for codon, weight in _LUNG_CODON_WEIGHTS.items()
}


class TissueCodonConfig(BaseConfig):
    target_tissue: Literal["lung", "kidney"] = ConfigField(
        default="lung",
        title="Target tissue",
        description="Tissue whose codon optimality pattern drives scoring",
    )


def _tissue_weights(tissue: str) -> dict[str, float]:
    if tissue == "kidney":
        return _KIDNEY_CODON_WEIGHTS
    return _LUNG_CODON_WEIGHTS


@constraint(
    key="tissue-codon",
    label="Tissue Codon Usage",
    config=TissueCodonConfig,
    description="Score codons by tissue-specific enrichment from CUSTOM PTR models",
    tools_called=[],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def tissue_codon_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: TissueCodonConfig,
) -> list[ConstraintOutput]:
    weights = _tissue_weights(config.target_tissue)
    max_weight = max(weights.values())

    results: list[ConstraintOutput] = []
    for (seq,) in input_sequences:
        seq_str = seq.sequence.upper()
        codon_count = len(seq_str) // 3
        if codon_count == 0:
            results.append(ConstraintOutput(score=1.0, metadata={"mean_tissue_score": 0.0}))
            continue

        relative_scores: list[float] = []
        for index in range(codon_count):
            codon = seq_str[index * 3 : index * 3 + 3]
            if len(codon) < 3 or any(base not in "ACGT" for base in codon):
                relative_scores.append(0.0)
                continue
            relative_scores.append(weights.get(codon, 1.0) / max_weight)

        mean_score = sum(relative_scores) / len(relative_scores)
        results.append(
            ConstraintOutput(
                score=min(1.0, max(0.0, 1.0 - mean_score)),
                metadata={"mean_tissue_score": mean_score, "codons_scored": codon_count},
            )
        )
    return results
