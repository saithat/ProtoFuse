import pytest
from proto_language.core import Sequence
from proto_language.generator import SemigreedyMutationGenerator
from proto_language.optimizer.mcmc_optimizer import MCMCOptimizer
from proto_tools import Structure

import protofuse.phillip.program_builders as program_builders_module
from protofuse.phillip.program_builders import (
    build_ligandmpnn_enzyme_redesign_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.score_only_structure import (
    score_only_esmfold_plddt_constraint,
)


def test_ligandmpnn_fixture_is_valid() -> None:
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    assert spec.global_parameters["workload"] == "ligandmpnn_enzyme_redesign"
    assert spec.global_parameters["enzyme_pdb"] == "3HTB"
    assert spec.paper.identifier == "protofuse-ligandmpnn-esmfold-joint-v2"
    assert {dependency.name for dependency in spec.model_dependencies} == {
        "LigandMPNN",
        "ESMFold",
    }


def test_ligandmpnn_smoke_build_program(monkeypatch: pytest.MonkeyPatch) -> None:
    pdb = (
        "".join(
            f"ATOM  {position:5d}  CA  ALA A{position:4d}    "
            f"{position:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 90.00           C\n"
            for position in range(1, 164)
        )
        + "END\n"
    )
    monkeypatch.setattr(
        program_builders_module,
        "_target_structure_from_pdb",
        lambda _pdb_id: Structure(structure=pdb, structure_format="pdb"),
    )
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_ligandmpnn_enzyme_redesign_program(params)

    optimizer = program.optimizers[0]
    assert isinstance(optimizer, MCMCOptimizer)
    assert optimizer.config.num_steps == 5
    generator = optimizer.generators[0]
    assert isinstance(generator, SemigreedyMutationGenerator)
    assert generator.config.clear_logits is True
    assert generator.config.exclude_current is True
    assert len(generator.config.frozen_positions or []) == 155
    enzyme = program.constructs[0].segments[0]
    original = enzyme.original_sequence.sequence
    enzyme.proposal_sequences = [Sequence(sequence=original, sequence_type="protein")]
    generator._set_program_seed(123)  # noqa: SLF001 - exercise the real seeded proposal path
    generator.sample()
    proposed = enzyme.proposal_sequences[0].sequence
    changed = [
        index
        for index, (left, right) in enumerate(zip(original, proposed, strict=True))
        if left != right
    ]
    assert len(changed) == 1
    assert changed[0] + 1 in {62, 64, 91, 92, 94, 96, 119, 121}
    assert enzyme.sequence_length == 163
    assert {item.label for item in optimizer.constraints} == {
        "mpnn_probability",
        "structure_plddt",
        "protein_length",
    }
    by_label = {item.label: item for item in optimizer.constraints}
    assert by_label["mpnn_probability"].threshold is None
    assert by_label["mpnn_probability"].weight == pytest.approx(1.0)
    assert by_label["structure_plddt"].threshold is None
    assert by_label["structure_plddt"].weight == pytest.approx(0.75)
    assert by_label["structure_plddt"].function is score_only_esmfold_plddt_constraint
