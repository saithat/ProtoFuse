"""Score-only structure objectives for learned-fusion experiments.

The stock Proto structure-confidence constraints attach the predicted structure to
their output.  That is useful when a later step consumes the structure, but it makes
the constraint ineligible for ProtoFuse's sequence-only surrogate path.  The
wrappers in this module are deliberately narrow: they still run the full parent
model and preserve its scalar objective, but discard an otherwise-unused structure.
"""

from __future__ import annotations

import math
from typing import Any

from proto_language.constraint import structure_plddt_constraint
from proto_language.constraint.constraint_registry import constraint
from proto_language.constraint.protein_structure.structure_constraint_config import (
    StructureBasedConstraintConfig,
)
from proto_language.core import ConstraintOutput, Sequence
from proto_language.utils.base import BaseConfig, ConfigField


class ScoreOnlyESMFoldPLDDTConfig(BaseConfig):
    """ESMFold confidence objective plus a post-hoc reporting target."""

    minimum_plddt_reporting_target: float = ConfigField(
        default=70.0,
        title="Minimum pLDDT reporting target",
        description=(
            "Reported alongside the continuous objective; it is not a hard optimizer "
            "threshold and is never enforced by the surrogate."
        ),
        ge=0.0,
        le=100.0,
    )


@constraint(
    key="score-only-esmfold-plddt",
    label="Score-Only ESMFold pLDDT",
    config=ScoreOnlyESMFoldPLDDTConfig,
    description=(
        "Run ESMFold and return its exact pLDDT energy without attaching the unused structure"
    ),
    uses_gpu=True,
    tools_called=["esmfold-prediction"],
    category="protein_structure",
    supported_sequence_types=["protein"],
)
def score_only_esmfold_plddt_constraint(
    input_sequences: list[tuple[Sequence, ...]],
    config: ScoreOnlyESMFoldPLDDTConfig,
) -> list[ConstraintOutput]:
    """Return ``1 - normalized_pLDDT`` while dropping structure/PDB payloads.

    The parent ESMFold call is unchanged.  Only its unused structure side output is
    removed so the objective can participate in a score-only fusion group.  The
    mandatory final-validation stage therefore still invokes ESMFold itself.
    """

    parent_outputs = structure_plddt_constraint(
        input_sequences,
        config=StructureBasedConstraintConfig(structure_tool="esmfold"),
    )
    outputs: list[ConstraintOutput] = []
    for parent in parent_outputs:
        parent_metadata = parent.metadata if isinstance(parent.metadata, dict) else {}
        metadata: dict[str, Any] = {
            key: value for key, value in parent_metadata.items() if key != "pdb_output"
        }
        metric = metadata.get("avg_plddt")
        metadata["minimum_plddt_reporting_target"] = config.minimum_plddt_reporting_target
        normalized_plddt = float(metric) if isinstance(metric, int | float) else None
        plddt_percent = (
            normalized_plddt * 100.0
            if normalized_plddt is not None
            and math.isfinite(normalized_plddt)
            and 0.0 <= normalized_plddt <= 1.0
            else None
        )
        metadata["avg_plddt_percent"] = plddt_percent
        metadata["meets_plddt_reporting_target"] = (
            plddt_percent >= config.minimum_plddt_reporting_target
            if plddt_percent is not None
            else None
        )
        metadata["score_only"] = True
        outputs.append(
            ConstraintOutput(
                score=float(parent.score),
                metadata=metadata,
            )
        )
    return outputs
