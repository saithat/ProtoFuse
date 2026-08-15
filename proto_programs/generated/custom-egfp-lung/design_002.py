"""Smoke-tier CUSTOM eGFP lung pool member for fast local sanity checks."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_custom_egfp_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier="smoke")
    return build_custom_egfp_program(params)
