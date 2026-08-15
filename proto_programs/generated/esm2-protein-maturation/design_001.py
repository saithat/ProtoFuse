"""Full-tier ESM-2 protein maturation (129 aa lysozyme, 200 MCMC steps).

Represents one region-pass in the iterative_refinement topology matching dnachisel-num1.
ESM-2 proposes masked mutations; ESMFold pLDDT/PAE gate developability.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_esm2_protein_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("esm2-protein-maturation")
    params = resolve_workload_params(spec, tier="full")
    return build_esm2_protein_maturation_program(params, region_pass=0)
