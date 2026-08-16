"""Full-tier Evo 2 regulatory design for the EVO2 Morse pattern.

Generate 128-bp chunks with Evo 2 and retain separate Enformer and four-replicate Borzoi pattern losses; the paper ranks their 0.5/0.5 mean.
"""

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
    return build_evo2_regulatory_design_program(params, morse_pattern=". ...- --- ..---", dot_bp=384)
