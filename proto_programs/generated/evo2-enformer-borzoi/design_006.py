"""Complete budgeted Evo 2/Enformer/Borzoi ARC reproduction for a three-hour campaign. It uses a 4,096-base prompt, designs all 4,096 bases in 32 128-base iterations, retains one prompt, and samples six proposals per iteration. The full ARC target is compressed to the smallest Enformer-resolvable dot width; this is not paper-length."""

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
    return build_evo2_regulatory_design_program({**params, "segment_length_bp": 4096, "evo2_generator_prompt_bp": 4096, "num_results": 1}, morse_pattern=".- .-. -.-.", dot_bp=128, proposals_per_result=6)
