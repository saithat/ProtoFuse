"""Full-length ARC regulatory design at the paper's 6-token-per-designed-bp inference-scaling point. It retains one prompt and samples six 128-bp chunks per iteration while preserving the full genomic context and both paper scoring models."""

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
    return build_evo2_regulatory_design_program({**params, "num_results": 1}, morse_pattern=".- .-. -.-.", dot_bp=384, proposals_per_result=6)
