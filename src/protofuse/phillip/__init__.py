"""Phillip's paper-to-Proto end-to-end track."""

from protofuse.phillip.compiler import compile_proto_plan
from protofuse.phillip.contracts import MethodologySpec, ProtoPlan
from protofuse.phillip.extractor import ExtractionBackend, ScientificAgent
from protofuse.phillip.generator import finalize_collection
from protofuse.phillip.pipeline import PipelineResult, run_pipeline
from protofuse.phillip.topology import recommend_topologies

__all__ = [
    "ExtractionBackend",
    "MethodologySpec",
    "PipelineResult",
    "ProtoPlan",
    "ScientificAgent",
    "compile_proto_plan",
    "finalize_collection",
    "recommend_topologies",
    "run_pipeline",
]
