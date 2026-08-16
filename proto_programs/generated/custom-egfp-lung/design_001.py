"""Full paper-scale CUSTOM eGFP-to-lung reproduction (717 bp, 1,000 candidates).

Uses the authors' released synonymous generator, five-metric ranking,
homopolymer filter, and top-10 selection.
Paper: Hernandez-Alias et al., Genome Biology 2023, 10.1186/s13059-023-02868-2.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_custom_egfp_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier="full")
    return build_custom_egfp_program(params)
