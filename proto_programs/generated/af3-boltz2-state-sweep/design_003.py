"""Full-tier cross-model conformational diagnostic.

For one of five explicit implementation seeds, score the fixed sequence with separate AlphaFold3 and Boltz-2 TM-scores to each of two reference states. This is a ProtoFuse joint-surrogate extension; the paper uses AlphaFold3 only as an external baseline.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_af3_boltz2_state_sweep_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("af3-boltz2-state-sweep")
    params = resolve_workload_params(spec, tier="full")
    return build_af3_boltz2_state_sweep_program(params, seed=2)
