"""Full-tier RFdiffusion3 PPI benchmark target.

Generate 400 backbones, sample four ProteinMPNN sequences per backbone, use the paper's exact target crop, atom hotspots, and binder origin, then retain ProteinMPNN probability plus the conjunctive AlphaFold3 paper gate with binder-pTM, minimum interchain PAE, and target-aligned binder RMSD.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_rfdiffusion3_af3_ppi_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("rfdiffusion3-af3-ppi")
    params = resolve_workload_params(spec, tier="full")
    return build_rfdiffusion3_af3_ppi_program(params, target_index=4)
