"""Versioned contracts for Phillip's paper-to-Proto pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExecutionDevice = Literal["local", "modal"]


class ContractModel(BaseModel):
    """Strict base model so an agent cannot silently invent new schema fields."""

    model_config = ConfigDict(extra="forbid")


class Evidence(ContractModel):
    """A location in the source supporting an extracted claim."""

    quote: str = Field(min_length=1, max_length=600)
    section: str | None = None
    page: int | None = Field(default=None, ge=1)


class PaperRef(ContractModel):
    title: str = Field(min_length=1)
    identifier: str | None = Field(
        default=None, description="DOI, PMID, arXiv identifier, or Paperclip path"
    )
    source_path: str | None = None
    full_text_identifier: str | None = Field(
        default=None,
        description=(
            "DOI whose full text carries the quoted methods, when that is not the cited "
            "publication — typically a preprint, whose Methods survive journal condensing"
        ),
    )


class ComponentSpec(ContractModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)


class GeneratorSpec(ComponentSpec):
    output: Literal["dna", "rna", "protein", "structure", "measurement", "other"]


class ConstraintSpec(ComponentSpec):
    metric: str = Field(min_length=1)
    direction: Literal["minimize", "maximize", "range", "match", "filter"]
    weight: float | None = Field(default=None, ge=0)


class OptimizerSpec(ComponentSpec):
    strategy: str = Field(min_length=1)
    stopping_criteria: dict[str, Any] = Field(default_factory=dict)


class ModelDependency(ContractModel):
    name: str = Field(min_length=1)
    version_or_checkpoint: str | None = None
    provider: str | None = None
    purpose: str = Field(min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)


class WorkflowStep(ContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    operation: str = Field(min_length=1)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)


class WorkflowEdge(ContractModel):
    source: str
    target: str
    artifact: str = Field(min_length=1)


class WorkflowTopology(ContractModel):
    steps: list[WorkflowStep] = Field(min_length=1)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def edges_reference_known_steps(self) -> WorkflowTopology:
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("workflow step ids must be unique")
        unknown = {
            endpoint
            for edge in self.edges
            for endpoint in (edge.source, edge.target)
            if endpoint not in ids
        }
        if unknown:
            raise ValueError(f"workflow edges reference unknown steps: {sorted(unknown)}")
        return self


class SelectionThreshold(ContractModel):
    name: str
    metric: str
    operator: Literal["<", "<=", ">", ">=", "==", "between"]
    value: float | int | str | list[float]
    unit: str | None = None
    applies_to: str
    evidence: list[Evidence] = Field(default_factory=list)


class ExperimentalMeasurement(ContractModel):
    name: str
    value: float | int | str | None = None
    unit: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    role: Literal["input", "objective", "validation", "feedback"]
    evidence: list[Evidence] = Field(default_factory=list)


class MethodologySpec(ContractModel):
    """Phillip's evidence-grounded paper-to-Proto methodology contract."""

    schema_version: Literal["1.0"] = "1.0"
    paper: PaperRef
    generators: list[GeneratorSpec] = Field(default_factory=list)
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    optimizers: list[OptimizerSpec] = Field(default_factory=list)
    model_dependencies: list[ModelDependency] = Field(default_factory=list)
    global_parameters: dict[str, Any] = Field(default_factory=dict)
    workflow: WorkflowTopology
    selection_thresholds: list[SelectionThreshold] = Field(default_factory=list)
    experimental_measurements: list[ExperimentalMeasurement] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class TopologyKind(StrEnum):
    PROPOSE_SCORE_SELECT = "propose_score_select"
    ITERATIVE_REFINEMENT = "iterative_refinement"
    STAGED_FILTER = "staged_filter"
    MULTIOBJECTIVE_SEARCH = "multiobjective_search"
    CLOSED_LOOP_EXPERIMENT = "closed_loop_experiment"


class TopologyRecommendation(ContractModel):
    topology: TopologyKind
    score: float = Field(ge=0, le=1)
    reasons: list[str]


class ComponentBinding(ContractModel):
    extracted_name: str
    proto_symbol: str | None = None
    status: Literal["bound", "unresolved"]


class ProtoPlan(ContractModel):
    """A reviewable plan; it is executable only when every binding is resolved."""

    schema_version: Literal["1.0"] = "1.0"
    paper: PaperRef
    topology: TopologyKind
    device: ExecutionDevice = "local"
    bindings: list[ComponentBinding]
    workflow: WorkflowTopology
    executable: bool
    unresolved: list[str]

    @model_validator(mode="after")
    def executable_requires_resolved_bindings(self) -> ProtoPlan:
        unresolved_bindings = [
            item.extracted_name for item in self.bindings if item.status != "bound"
        ]
        if self.executable and (unresolved_bindings or self.unresolved):
            raise ValueError("an executable plan cannot contain unresolved components")
        return self
