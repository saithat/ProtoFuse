"""Smoke-tier DNA Chisel NUM1 MCMC program for fast local sanity checks."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_dnachisel_num1_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("dnachisel-num1")
    params = resolve_workload_params(spec, tier="smoke")
    return build_dnachisel_num1_program(params, region_pass=0)
