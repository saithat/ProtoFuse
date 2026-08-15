"""Smoke-tier ESM-2 protein maturation (80 aa truncated eGFP, 50 MCMC steps)."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_esm2_protein_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("esm2-protein-maturation")
    params = resolve_workload_params(spec, tier="smoke")
    return build_esm2_protein_maturation_program(params, region_pass=0)
