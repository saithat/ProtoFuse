"""Phillip's paper-to-Proto end-to-end track."""

from protofuse.phillip.compiler import compile_proto_plan
from protofuse.phillip.extractor import ExtractionBackend, ScientificAgent
from protofuse.phillip.pipeline import PipelineResult, run_pipeline
from protofuse.phillip.topology import recommend_topologies

__all__ = [
    "ExtractionBackend",
    "PipelineResult",
    "ScientificAgent",
    "compile_proto_plan",
    "recommend_topologies",
    "run_pipeline",
]
