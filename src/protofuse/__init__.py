"""ProtoFuse public API."""

from protofuse.checkpoints import run_with_checkpoints
from protofuse.runtime import discover_fusions, optimize, optimize_with_report, register_fusion

__all__ = [
    "discover_fusions",
    "optimize",
    "optimize_with_report",
    "register_fusion",
    "run_with_checkpoints",
]

__version__ = "0.1.0"
