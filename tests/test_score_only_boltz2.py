from typing import Any

import pytest
from proto_language.core import ConstraintOutput, Sequence
from proto_tools import Structure

import protofuse.phillip.score_only_structure as score_only_module
from protofuse.phillip.score_only_structure import (
    ScoreOnlyBoltz2Config,
    score_only_boltz2_iptm_constraint,
)


def test_score_only_boltz2_iptm_preserves_score_and_drops_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structure = Structure(
        structure=(
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 90.00           C\n"
            "END\n"
        ),
        structure_format="pdb",
    )

    def fake_parent(inputs: Any, *, config: Any) -> list[ConstraintOutput]:
        assert config.structure_tool == "boltz2"
        assert config.boltz2_config.use_msa is False
        return [
            ConstraintOutput(
                score=0.24,
                metadata={
                    "iptm": 0.76,
                    "pdb_output": structure.structure,
                    "structure_tool": "boltz2",
                },
                structures=(structure, None),
            )
            for _ in inputs
        ]

    monkeypatch.setattr(score_only_module, "structure_iptm_constraint", fake_parent)
    outputs = score_only_boltz2_iptm_constraint(
        [
            (
                Sequence(sequence="ACDE", sequence_type="protein"),
                Sequence(sequence="FGHI", sequence_type="protein"),
            )
        ],
        config=ScoreOnlyBoltz2Config(boltz2_config={"use_msa": False}),
    )

    assert len(outputs) == 1
    assert outputs[0].score == pytest.approx(0.24)
    assert outputs[0].structures == ()
    assert outputs[0].logits == ()
    assert "pdb_output" not in outputs[0].metadata
    assert outputs[0].metadata["iptm"] == pytest.approx(0.76)
    assert outputs[0].metadata["score_only"] is True
