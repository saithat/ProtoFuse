"""Full-tier RFdiffusion3 PPI benchmark target.

Generate 400 backbones, sample four ProteinMPNN sequences per backbone, and retain separate ProteinMPNN probability, AlphaFold3 ipTM-proxy, and AlphaFold3 mean-PAE-proxy scores. Paper binder-pTM and minimum interchain pAE endpoints remain separate benchmark measurements.
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
    return build_rfdiffusion3_af3_ppi_program(params, target_index=2)
