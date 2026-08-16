"""Full-tier RFdiffusion3+Boltz-2 cycling binder (70 aa, 10 cycles).

Bootstrap via RFdiffusion3+MPNN, then ProteinMPNN redesign conditioned on
Boltz-2 folds against CXCR4 chain A (PDB 4RWS).
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_rfdiffusion3_boltz2_binder_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("rfdiffusion3-boltz2-binder")
    params = resolve_workload_params(spec, tier="full")
    return build_rfdiffusion3_boltz2_binder_program(params)
