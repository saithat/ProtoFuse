"""Full-tier symmetric oligomer ring design (80 aa monomer, C6, n_pool=1000).

Represents one pool member in the propose-score-select loop: random-protein
mutation with rejection sampling under ESMFold symmetry, globularity, Rg,
structure-composite, and overall-protein-quality constraints.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_symmetric_oligomer_ring_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier="full")
    return build_symmetric_oligomer_ring_program(params)
