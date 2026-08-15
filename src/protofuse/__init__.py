"""ProtoFuse public API."""

from protofuse.runtime import optimize, optimize_with_report, register_fusion

__all__ = [
    "optimize",
    "optimize_with_report",
    "register_fusion",
]

__version__ = "0.1.0"
