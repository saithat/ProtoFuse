"""Full-tier query-only Boltz-2 pair-representation-scaling slice.

Use beta=-0.75 and implementation seed 3 for five Boltz-2 draws, with separate TM-scores to both reference states. Proto and ProtoFuse must use this same backend, input, and seed. AlphaFold 3 and paper-matched MSAs are optional validation recipes, not execution gates.
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
    return build_af3_boltz2_state_sweep_program(params, seed=3, beta=-0.75)
