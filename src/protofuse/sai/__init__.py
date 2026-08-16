"""Sai's automatic learned-fusion optimizer."""

from protofuse.sai.analyzer import LoadedReviewedProgram, load_reviewed_program
from protofuse.sai.artifacts import (
    FusionManifest,
    LoadedFusionArtifact,
    load_fusion_artifact,
)
from protofuse.sai.optimizer import OptimizationResult, optimize_program
from protofuse.sai.profiling import ConstraintProfile, TraceProfile, profile_traces
from protofuse.sai.registry import FusionBundle, FusionRegistry
from protofuse.sai.router import (
    BatchSelectiveRouter,
    GateDecision,
    RoutedResult,
    SelectiveRouter,
    SurrogatePrediction,
)
from protofuse.sai.signatures import (
    ProgramSignature,
    StepGroupSignature,
    program_signature,
    step_group_signature,
)
from protofuse.sai.tracing import JsonlTraceWriter, TraceRow, trace_program_constraints

__all__ = [
    "BatchSelectiveRouter",
    "ConstraintProfile",
    "FusionManifest",
    "FusionBundle",
    "FusionRegistry",
    "GateDecision",
    "JsonlTraceWriter",
    "LoadedFusionArtifact",
    "LoadedReviewedProgram",
    "OptimizationResult",
    "ProgramSignature",
    "RoutedResult",
    "SelectiveRouter",
    "StepGroupSignature",
    "SurrogatePrediction",
    "TraceRow",
    "TraceProfile",
    "load_fusion_artifact",
    "load_reviewed_program",
    "optimize_program",
    "profile_traces",
    "program_signature",
    "step_group_signature",
    "trace_program_constraints",
]
