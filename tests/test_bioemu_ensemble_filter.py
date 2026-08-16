from typing import Any

import pytest
from proto_language.core import ConstraintOutput, Sequence
from proto_language.optimizer.mcmc_optimizer import MCMCOptimizer
from proto_tools import Structure

import protofuse.phillip.program_builders as program_builders_module
import protofuse.phillip.score_only_structure as score_only_module
from protofuse.phillip.program_builders import (
    build_bioemu_ensemble_filter_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.score_only_structure import (
    ScoreOnlyESMFoldPLDDTConfig,
    score_only_esmfold_plddt_constraint,
)


def test_bioemu_fixture_is_valid() -> None:
    spec = load_fixture_spec("bioemu-ensemble-filter")
    assert spec.global_parameters["workload"] == "bioemu_ensemble_filter"
    assert spec.global_parameters["target_pdb"] == "2LYZ"
    assert spec.paper.identifier == "protofuse-bioemu-esmfold-joint-v2"
    assert {dependency.name for dependency in spec.model_dependencies} == {
        "BioEmu",
        "ESM-2",
        "ESMFold",
    }


def test_bioemu_smoke_build_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        program_builders_module,
        "_target_structure_from_pdb",
        lambda _pdb_id: Structure(
            structure=(
                "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 90.00           C\n"
                "END\n"
            ),
            structure_format="pdb",
        ),
    )
    spec = load_fixture_spec("bioemu-ensemble-filter")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_bioemu_ensemble_filter_program(params)

    optimizer = program.optimizers[0]
    assert isinstance(optimizer, MCMCOptimizer)
    assert optimizer.config.num_steps == 5
    segment = program.constructs[0].segments[0]
    assert segment.sequence_length == 80
    assert {item.label for item in optimizer.constraints} == {
        "ensemble_rmsd",
        "structure_plddt",
        "protein_length",
    }
    by_label = {item.label: item for item in optimizer.constraints}
    assert by_label["ensemble_rmsd"].threshold is None
    assert by_label["ensemble_rmsd"].weight == pytest.approx(1.0)
    assert by_label["structure_plddt"].threshold is None
    assert by_label["structure_plddt"].weight == pytest.approx(0.5)
    assert by_label["structure_plddt"].function is score_only_esmfold_plddt_constraint
    assert all(
        not slot.requires_structure and not slot.requires_logits
        for slot in by_label["structure_plddt"]._input_slots
    )


def test_score_only_esmfold_wrapper_preserves_score_and_drops_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structure = Structure(
        structure=(
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 90.00           C\nEND\n"
        ),
        structure_format="pdb",
    )

    def fake_parent(inputs: Any, *, config: Any) -> list[ConstraintOutput]:
        assert config.structure_tool == "esmfold"
        return [
            ConstraintOutput(
                score=0.18,
                metadata={
                    "avg_plddt": 0.82,
                    "pdb_output": structure.structure,
                    "structure_tool": "esmfold",
                },
                structures=(structure,),
            )
            for _ in inputs
        ]

    monkeypatch.setattr(score_only_module, "structure_plddt_constraint", fake_parent)
    outputs = score_only_esmfold_plddt_constraint(
        [(Sequence(sequence="ACDE", sequence_type="protein"),)],
        config=ScoreOnlyESMFoldPLDDTConfig(
            minimum_plddt_reporting_target=70.0,
        ),
    )

    assert len(outputs) == 1
    assert outputs[0].score == pytest.approx(0.18)
    assert outputs[0].structures == ()
    assert outputs[0].logits == ()
    assert "pdb_output" not in outputs[0].metadata
    assert outputs[0].metadata["avg_plddt_percent"] == pytest.approx(82.0)
    assert outputs[0].metadata["meets_plddt_reporting_target"] is True
