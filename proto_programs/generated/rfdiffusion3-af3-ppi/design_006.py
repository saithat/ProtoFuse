"""Smoke-tier RFdiffusion3/ProteinMPNN/AlphaFold3 joint-objective build for the first PPI benchmark target."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_rfdiffusion3_af3_ppi_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("rfdiffusion3-af3-ppi")
    params = resolve_workload_params(spec, tier="smoke")
    return build_rfdiffusion3_af3_ppi_program(params, target_index=0)
