"""Shared integration from extracted methodology to Proto planning."""

from protofuse.integration.compiler import compile_proto_plan
from protofuse.integration.registry import DNA_BASELINE_REGISTRY, DNA_CHISEL_REGISTRY
from protofuse.integration.scenarios import validate_integrations

__all__ = [
    "DNA_BASELINE_REGISTRY",
    "DNA_CHISEL_REGISTRY",
    "compile_proto_plan",
    "validate_integrations",
]
