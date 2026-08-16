"""Full-tier BioEmu ensemble filter (129 aa lysozyme, 100 MCMC steps).

ESM-2 proposals filtered by BioEmu ensemble RMSD vs lysozyme PDB 2LYZ
and ESMFold developability.
"""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_bioemu_ensemble_filter_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("bioemu-ensemble-filter")
    params = resolve_workload_params(spec, tier="full")
    return build_bioemu_ensemble_filter_program(params)
