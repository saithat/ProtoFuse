"""Smoke-tier PPI interface specificity for fast GPU sanity checks (20 steps, interface patch 1, ESM-2 proposals)."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_ppi_interface_specificity_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier="smoke")
    return build_ppi_interface_specificity_program(params, region_pass=0)
