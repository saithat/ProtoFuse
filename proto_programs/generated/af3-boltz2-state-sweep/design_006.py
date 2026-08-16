"""Smoke-tier AlphaFold3/Boltz-2 dual-state TM-score diagnostic on adenylate kinase."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_af3_boltz2_state_sweep_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("af3-boltz2-state-sweep")
    params = resolve_workload_params(spec, tier="smoke")
    return build_af3_boltz2_state_sweep_program(params, seed=0)
