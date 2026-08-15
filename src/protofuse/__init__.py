"""ProtoFuse public API."""

from protofuse.phillip.contracts import MethodologySpec, ProtoPlan
from protofuse.runtime import optimize, optimize_with_report, register_fusion

__all__ = [
    "MethodologySpec",
    "ProtoPlan",
    "optimize",
    "optimize_with_report",
    "register_fusion",
]

__version__ = "0.1.0"
