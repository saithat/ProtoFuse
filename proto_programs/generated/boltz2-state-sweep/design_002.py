"""Smoke-tier Boltz-2 state sweep (adenylate kinase 214 aa, 6 draws).

Soluble domain-motion proxy for fast GPU sanity checks before the
full XylE IOMemP transporter benchmark.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_boltz2_state_sweep_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("boltz2-state-sweep")
    params = resolve_workload_params(spec, tier="smoke")
    return build_boltz2_state_sweep_program(params)
