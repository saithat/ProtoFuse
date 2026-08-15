"""Sai's automatic learned-fusion optimizer."""

from protofuse.sai.optimizer import OptimizationResult, optimize_program
from protofuse.sai.registry import FusionBundle, FusionRegistry
from protofuse.sai.router import GateDecision, RoutedResult, SelectiveRouter, SurrogatePrediction

__all__ = [
    "FusionBundle",
    "FusionRegistry",
    "GateDecision",
    "OptimizationResult",
    "RoutedResult",
    "SelectiveRouter",
    "SurrogatePrediction",
    "optimize_program",
]
