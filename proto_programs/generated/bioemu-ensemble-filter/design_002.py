"""Smoke-tier BioEmu ensemble filter (80 aa truncated lysozyme, 5 steps, 1 BioEmu sample)."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_bioemu_ensemble_filter_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("bioemu-ensemble-filter")
    params = resolve_workload_params(spec, tier="smoke")
    return build_bioemu_ensemble_filter_program(params)
