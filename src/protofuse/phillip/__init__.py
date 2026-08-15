"""Phillip's paper-to-Proto end-to-end track."""

from protofuse.phillip.compiler import (
    UnresolvedBindingsError,
    compile_proto_plan,
    require_resolved_plan,
)
from protofuse.phillip.contracts import MethodologySpec, ProtoPlan
from protofuse.phillip.extractor import ExtractionBackend, ScientificAgent
from protofuse.phillip.generator import (
    finalize_collection,
    generate_program_sources,
    validate_program_source,
    write_design_programs,
)
from protofuse.phillip.pipeline import PipelineResult, run_pipeline
from protofuse.phillip.topology import recommend_topologies

__all__ = [
    "ExtractionBackend",
    "MethodologySpec",
    "PipelineResult",
    "ProtoPlan",
    "ScientificAgent",
    "UnresolvedBindingsError",
    "compile_proto_plan",
    "finalize_collection",
    "generate_program_sources",
    "recommend_topologies",
    "require_resolved_plan",
    "run_pipeline",
    "validate_program_source",
    "write_design_programs",
]
