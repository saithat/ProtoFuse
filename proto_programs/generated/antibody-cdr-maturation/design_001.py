"""Full-tier antibody CDR maturation (121-aa nanobody, 100 MCMC steps, 3 CDR passes).

Represents one region-pass in the region-local solver: ESM-2 mutations within
the active CDR, AbLang naturalness, ESMFold ipTM vs peptide antigen stub,
protein complexity, and gap Gini vs seed framework.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_antibody_cdr_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier="full")
    return build_antibody_cdr_maturation_program(params, region_pass=0)
