"""Full-tier pair-representation-scaling protocol slice.

Use beta=0.6 and implementation seed 1 for five AlphaFold3 and five Boltz-2 draws, with separate TM-scores to both reference states. Execution requires explicitly registered reviewed backends and has no unscaled fallback.
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
    return build_af3_boltz2_state_sweep_program(params, seed=1, beta=0.6)
