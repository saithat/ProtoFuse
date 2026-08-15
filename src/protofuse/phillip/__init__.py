"""Phillip's paper-to-plan end-to-end track."""

from protofuse.phillip.benchmark import (
    BenchmarkCompareResult,
    compare_benchmark,
    run_baseline_benchmark,
    run_candidate_benchmark,
)
from protofuse.phillip.handoff import HandoffBundle, build_handoff_bundle, write_handoff_bundle
from protofuse.phillip.pipeline import PipelineResult, run_pipeline
from protofuse.phillip.proto_builder import build_baseline_program

__all__ = [
    "BenchmarkCompareResult",
    "HandoffBundle",
    "PipelineResult",
    "build_baseline_program",
    "build_handoff_bundle",
    "compare_benchmark",
    "run_baseline_benchmark",
    "run_candidate_benchmark",
    "run_pipeline",
    "write_handoff_bundle",
]
