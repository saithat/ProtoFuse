"""Full-tier CUSTOM eGFP lung pool member (720 bp, 100 MCMC steps).

Represents one candidate in CUSTOM's n_pool=1000 propose-score-select loop.
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
