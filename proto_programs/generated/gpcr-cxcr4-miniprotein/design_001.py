"""Full-tier CXCR4 miniprotein binder design (70 aa, 10 rejection samples).

Represents one in-silico design batch from Muratspahić et al., Nature 2026,
10.1038/s41586-026-10656-8 (dCX1_001 CXCR4 antagonist case).
RFdiffusion3+MPNN replaces paper RFdiffusion v1; Boltz-2 replaces AF2 filter.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_gpcr_cxcr4_miniprotein_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("gpcr-cxcr4-miniprotein")
    params = resolve_workload_params(spec, tier="full")
    return build_gpcr_cxcr4_miniprotein_program(params)
