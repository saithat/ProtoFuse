"""Full-tier Evo 2 regulatory design for the ARC Morse pattern with separate Enformer and Borzoi losses."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_evo2_regulatory_design_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("evo2-enformer-borzoi")
    params = resolve_workload_params(spec, tier="full")
    return build_evo2_regulatory_design_program(params, morse_pattern=".- .-. -.-.", dot_bp=384)
