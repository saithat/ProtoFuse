"""Full-tier PPI interface specificity (65-aa binder, 100 MCMC steps, 2 interface passes).

Represents one region-pass in the region-local solver: MPNN mutations within
the active interface patch, AF3/Boltz on-target scoring, AF3 off-target
specificity margin, and AF2 interface contact loss vs PD-L1 (4ZQK).
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_ppi_interface_specificity_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier="full")
    return build_ppi_interface_specificity_program(params, region_pass=0)
