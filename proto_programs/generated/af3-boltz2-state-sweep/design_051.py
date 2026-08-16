"""Smoke-tier audited query-only Boltz-2 pair-scaling binding check on adenylate kinase at beta=-0.15; AlphaFold 3 is an optional cross-check."""

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
    return build_af3_boltz2_state_sweep_program(params, seed=0, beta=-0.15)
