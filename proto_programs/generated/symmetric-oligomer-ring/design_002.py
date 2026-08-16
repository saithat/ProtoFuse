"""Smoke-tier symmetric oligomer ring design for fast GPU sanity checks (60 aa monomer, C3, n_pool=100)."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_symmetric_oligomer_ring_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier="smoke")
    return build_symmetric_oligomer_ring_program(params)
