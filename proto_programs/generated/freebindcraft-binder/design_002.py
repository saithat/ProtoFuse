"""Smoke-tier FreeBindCraft binder design (50 aa, 5 samples) for fast GPU sanity checks."""

from __future__ import annotations

from proto_language.core import Program

from protofuse.phillip.program_builders import (
    build_freebindcraft_binder_program,
    load_fixture_spec,
    resolve_workload_params,
)


def build_program() -> Program:
    spec = load_fixture_spec("freebindcraft-binder")
    params = resolve_workload_params(spec, tier="smoke")
    return build_freebindcraft_binder_program(params)
