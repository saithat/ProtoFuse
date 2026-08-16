"""Full-tier FreeBindCraft binder design (70 aa, 50 rejection samples).

Represents one in-silico design batch from the staged_filter topology:
FreeBindCraft hallucination → AF2 validation → rejection sampling.
Target: CXCR4 chain A from PDB 4RWS (compact benchmark epitope).
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_freebindcraft_binder_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("freebindcraft-binder")
    params = resolve_workload_params(spec, tier="full")
    return build_freebindcraft_binder_program(params)
