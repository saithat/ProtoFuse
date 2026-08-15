"""Smoke-tier antibody CDR maturation for fast GPU sanity checks (30 steps, CDR1 only)."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_antibody_cdr_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier="smoke")
    return build_antibody_cdr_maturation_program(params, region_pass=0)
