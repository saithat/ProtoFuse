"""Full-tier LigandMPNN enzyme active-site MCMC (3HTB, 100 steps).

Mutates active-site ordinals on a fixed holo backbone with
joint LigandMPNN probability and ESMFold pLDDT objectives.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_ligandmpnn_enzyme_redesign_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    params = resolve_workload_params(spec, tier="full")
    return build_ligandmpnn_enzyme_redesign_program(params)
