from proto_language.optimizer.cycling_optimizer import CyclingOptimizer

from protofuse.phillip.cycling_builders import _contiguous_position_spans
from protofuse.phillip.program_builders import (
    build_rfdiffusion3_boltz2_binder_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.score_only_structure import score_only_boltz2_iptm_constraint


def test_rfdiffusion_contig_spans_do_not_invent_missing_residues() -> None:
    positions = [
        *range(23, 67),
        *range(71, 229),
        *range(1002, 1165),
        *range(231, 304),
    ]

    assert _contiguous_position_spans(positions) == [
        (23, 66),
        (71, 228),
        (1002, 1164),
        (231, 303),
    ]


def test_rfdiffusion3_fixture_is_valid() -> None:
    spec = load_fixture_spec("rfdiffusion3-boltz2-binder")
    assert spec.global_parameters["workload"] == "rfdiffusion3_boltz2_binder"
    assert int(spec.global_parameters["num_steps"]) == 10


def test_rfdiffusion3_smoke_build_program() -> None:
    spec = load_fixture_spec("rfdiffusion3-boltz2-binder")
    params = resolve_workload_params(spec, tier="smoke")
    program = build_rfdiffusion3_boltz2_binder_program(params)

    optimizer = program.optimizers[0]
    assert isinstance(optimizer, CyclingOptimizer)
    assert optimizer.config.num_steps == 2
    binder = program.constructs[0].segments[0]
    assert binder.sequence_length == 50
    assert {item.label for item in optimizer.constraints} == {"iptm", "plddt", "length"}
    boltz_constraints = [
        item for item in optimizer.constraints if item.label in {"iptm", "plddt"}
    ]
    assert all(not item.function_config.boltz2_config.use_msa for item in boltz_constraints)
    constraints_by_label = {item.label: item for item in optimizer.constraints}
    assert constraints_by_label["iptm"].function is score_only_boltz2_iptm_constraint
    assert constraints_by_label["iptm"].threshold == 0.5
    assert constraints_by_label["plddt"].threshold == 0.3
