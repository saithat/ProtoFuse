"""Smoke-tier LigandMPNN + ESMFold joint optimization (5 MCMC steps)."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_ligandmpnn_enzyme_redesign_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    params = resolve_workload_params(spec, tier="smoke")
    return build_ligandmpnn_enzyme_redesign_program(params)
