"""Smoke-tier CXCR4 miniprotein binder design for fast GPU sanity checks."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_gpcr_cxcr4_miniprotein_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("gpcr-cxcr4-miniprotein")
    params = resolve_workload_params(spec, tier="smoke")
    return build_gpcr_cxcr4_miniprotein_program(params)
