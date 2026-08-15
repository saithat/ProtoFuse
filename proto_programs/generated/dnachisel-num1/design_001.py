"""Full-tier DNA Chisel NUM1 region-local MCMC program (936 bp, 200 steps).

Represents one region-pass / inner-refinement step in the NUM1 region-local solver.
Paper: DNA Chisel, 10.1093/bioinformatics/btaa558, Figure 1 NUM1 codon optimization.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_dnachisel_num1_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("dnachisel-num1")
    params = resolve_workload_params(spec, tier="full")
    return build_dnachisel_num1_program(params, region_pass=0)
