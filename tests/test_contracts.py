import pytest
from pydantic import ValidationError

from protofuse.phillip.contracts import MethodologySpec


def test_example_contract_loads(example_spec: MethodologySpec) -> None:
    assert example_spec.schema_version == "1.0"
    assert example_spec.workflow.steps[0].id == "generate"


def test_unknown_workflow_edge_is_rejected(example_payload: dict[str, object]) -> None:
    workflow = example_payload["workflow"]
    assert isinstance(workflow, dict)
    edges = workflow["edges"]
    assert isinstance(edges, list)
    edges[0]["target"] = "missing"  # type: ignore[index]

    with pytest.raises(ValidationError, match="unknown steps"):
        MethodologySpec.model_validate(example_payload)
